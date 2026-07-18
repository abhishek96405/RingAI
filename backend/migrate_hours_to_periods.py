"""
migrate_hours_to_periods.py

Tidy-up migration: convert any restaurant config day still in the OLD
operating-hours shape

    "monday": {"closed": False, "open": "09:00", "close": "21:00"}

to the NEW canonical shape

    "monday": {"closed": False, "last_call_offset_minutes": 0,
               "periods": [{"open": "09:00", "close": "21:00"}]}

IMPORTANT: this migration is NOT a prerequisite. Every hours reader
(gemini_service.calculate_is_open, reservation_service.get_reservation_slots,
calendar_service.calculate_available_slots, appointment_service.*) already reads
the OLD shape transparently via gemini_service.normalize_day_hours /
get_effective_periods and treats it as a single period with a 0-minute offset.
Running this script just normalizes stored documents so the DB matches what the
API now returns by default. The app works correctly whether or not it runs.

It is DRY-RUN by default. Re-run with  --commit  (or APPLY=true) to write.
It is idempotent: a day already in the new shape is left untouched, so running
it twice is safe.

Runs across every *_configs collection (restaurants + appointment verticals) so
the same hours convention applies everywhere.

Run:
    python migrate_hours_to_periods.py            # dry run, prints what it would do
    python migrate_hours_to_periods.py --commit   # actually applies
    APPLY=true python migrate_hours_to_periods.py  # same, via env flag
"""

import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

COMMIT = ("--commit" in sys.argv) or (os.environ.get("APPLY", "").lower() == "true")

# Every config collection that stores an operating_hours block.
CONFIG_COLLECTIONS = [
    "restaurant_configs",
    "clinic_configs",
    "salon_configs",
    "home_service_configs",
    "legal_configs",
]

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def log(msg):
    prefix = "APPLY " if COMMIT else "DRYRUN"
    print(f"[{prefix}] {msg}")


def _needs_migration(day_config) -> bool:
    """True if this day is in the OLD shape (has open/close, no periods list)."""
    if not isinstance(day_config, dict):
        return False
    if isinstance(day_config.get("periods"), list):
        return False  # already new shape
    return bool(day_config.get("open")) or bool(day_config.get("close"))


def _to_new_shape(day_config: dict) -> dict:
    """Convert one OLD-shape day to the NEW canonical shape."""
    new_day = {
        "closed": bool(day_config.get("closed", False)),
        "last_call_offset_minutes": int(day_config.get("last_call_offset_minutes", 0) or 0),
        "periods": [],
    }
    o = day_config.get("open")
    c = day_config.get("close")
    if o and c:
        new_day["periods"] = [{"open": o, "close": c}]
    return new_day


def migrate_operating_hours(operating_hours) -> tuple:
    """Return (new_operating_hours, changed_bool). Non-dict input is passed through."""
    if not isinstance(operating_hours, dict):
        return operating_hours, False
    changed = False
    new_hours = dict(operating_hours)
    for day, day_config in operating_hours.items():
        if _needs_migration(day_config):
            new_hours[day] = _to_new_shape(day_config)
            changed = True
    return new_hours, changed


async def main():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ringai_db")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"Connected to {db_name}. Mode: {'COMMIT' if COMMIT else 'DRY RUN'}\n")

    total_migrated = 0
    for coll_name in CONFIG_COLLECTIONS:
        coll = db[coll_name]
        try:
            configs = await coll.find({}, {"_id": 0}).to_list(5000)
        except Exception as e:
            log(f"skip {coll_name}: {e}")
            continue

        if not configs:
            continue

        coll_migrated = 0
        for cfg in configs:
            rid = cfg.get("restaurant_id") or cfg.get("id")
            oh = cfg.get("operating_hours")
            new_oh, changed = migrate_operating_hours(oh)
            if not changed:
                continue

            coll_migrated += 1
            total_migrated += 1
            old_days = [d for d in WEEKDAYS if _needs_migration((oh or {}).get(d))]
            log(f"{coll_name}/{rid}: migrate {len(old_days)} old-shape day(s): {old_days}")
            if COMMIT:
                await coll.update_one(
                    {"restaurant_id": rid} if cfg.get("restaurant_id") else {"id": rid},
                    {"$set": {"operating_hours": new_oh}},
                )

        if coll_migrated:
            log(f"{coll_name}: {coll_migrated} config(s) with old-shape days")

    if total_migrated == 0:
        print("No old-shape operating_hours found. Nothing to do.")
    else:
        print(
            f"\n{total_migrated} config(s) "
            + ("migrated." if COMMIT else "would be migrated (dry run — re-run with --commit to apply).")
        )
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
