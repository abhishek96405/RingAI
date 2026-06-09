"""
migrate_split_brain.py

One-off repair for businesses that were onboarded BEFORE the onboarding flow
started sending `business_type`. Those businesses ended up "split-brained":

  - their membership says   business_type = "restaurant"   (WRONG)
  - their business doc lives in db.restaurants               (WRONG)
  - their parsed services landed in db.menu_items            (WRONG)
  - BUT their config has    business_type = "salon" (etc.)   (the band-aid)

This script uses the config's business_type as the source of truth, then makes
every other store agree with it:

  1. memberships  -> set business_type to the real type
  2. business doc -> move db.restaurants -> db.salons (etc.), stamp business_type
  3. services     -> copy db.menu_items -> db.services (as ServiceItem shape)
  4. config       -> copy db.restaurant_configs -> db.salon_configs (etc.)

It is DRY-RUN by default. Re-run with  --commit  to actually write.
It is idempotent: running it twice is safe.

Run:
    python migrate_split_brain.py            # dry run, prints what it would do
    python migrate_split_brain.py --commit   # actually applies
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

APPOINTMENT_TYPES = ["clinic", "salon", "home_services", "legal"]

BUSINESS_COLL = {
    "restaurant": "restaurants",
    "clinic": "clinics",
    "salon": "salons",
    "home_services": "home_services",
    "legal": "legal",
}
CONFIG_COLL = {
    "restaurant": "restaurant_configs",
    "clinic": "clinic_configs",
    "salon": "salon_configs",
    "home_services": "home_service_configs",
    "legal": "legal_configs",
}

COMMIT = "--commit" in sys.argv


def log(msg):
    prefix = "APPLY " if COMMIT else "DRYRUN"
    print(f"[{prefix}] {msg}")


def menu_item_to_service(mi: dict, restaurant_id: str) -> dict:
    """Map a MenuItem doc to a ServiceItem doc."""
    return {
        "id": str(uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "name": mi.get("name", ""),
        "description": mi.get("description"),
        "duration_minutes": mi.get("duration_minutes", 60),
        "buffer_minutes": 15,
        # MenuItem.price and ServiceItem.price_cents are both "cents" in this codebase.
        "price_cents": mi.get("price", 0),
        "available": mi.get("available", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def main():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ringai_db")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"Connected to {db_name}. Mode: {'COMMIT' if COMMIT else 'DRY RUN'}\n")

    # Source of truth: configs that declare an appointment business_type.
    bad_configs = await db.restaurant_configs.find(
        {"business_type": {"$in": APPOINTMENT_TYPES}}, {"_id": 0}
    ).to_list(1000)

    if not bad_configs:
        print("No split-brain records found in db.restaurant_configs. Nothing to do.")
        client.close()
        return

    print(f"Found {len(bad_configs)} config(s) with an appointment business_type "
          f"living in restaurant_configs.\n")

    for cfg in bad_configs:
        rid = cfg.get("restaurant_id")
        btype = cfg.get("business_type")
        if not rid or btype not in BUSINESS_COLL:
            continue

        biz_coll = db[BUSINESS_COLL[btype]]
        cfg_coll = db[CONFIG_COLL[btype]]

        # Resolve a display name for logging.
        doc = await db.restaurants.find_one({"id": rid}, {"_id": 0})
        already_typed = await biz_coll.find_one({"id": rid}, {"_id": 0})
        name = (doc or already_typed or {}).get("name", "(unknown)")

        print(f"--- {name}  [{rid}]  ->  {btype} ---")

        # 1) memberships
        memberships = await db.memberships.find(
            {"restaurant_id": rid}, {"_id": 0}
        ).to_list(100)
        for m in memberships:
            if m.get("business_type") != btype:
                log(f"membership {m.get('id')}: business_type "
                    f"{m.get('business_type')!r} -> {btype!r}")
                if COMMIT:
                    await db.memberships.update_one(
                        {"id": m["id"]}, {"$set": {"business_type": btype}}
                    )

        # 2) business doc: db.restaurants -> typed collection
        if doc and not already_typed:
            doc["business_type"] = btype
            log(f"move business doc db.restaurants -> db.{BUSINESS_COLL[btype]} "
                f"(and stamp business_type={btype!r})")
            if COMMIT:
                await biz_coll.insert_one({k: v for k, v in doc.items() if k != "_id"})
                await db.restaurants.delete_one({"id": rid})
        elif already_typed and already_typed.get("business_type") != btype:
            log(f"stamp business_type={btype!r} on existing db.{BUSINESS_COLL[btype]} doc")
            if COMMIT:
                await biz_coll.update_one({"id": rid}, {"$set": {"business_type": btype}})
        elif doc and already_typed:
            log(f"business doc exists in BOTH db.restaurants and "
                f"db.{BUSINESS_COLL[btype]}; deleting the stray restaurants copy")
            if COMMIT:
                await db.restaurants.delete_one({"id": rid})

        # 3) services: db.menu_items -> db.services
        menu_items = await db.menu_items.find({"restaurant_id": rid}, {"_id": 0}).to_list(1000)
        existing_services = await db.services.count_documents({"restaurant_id": rid})
        if menu_items and existing_services == 0:
            log(f"convert {len(menu_items)} menu_item(s) -> services")
            if COMMIT:
                services = [menu_item_to_service(mi, rid) for mi in menu_items]
                await db.services.insert_many(services)
                await db.menu_items.delete_many({"restaurant_id": rid})
        elif menu_items and existing_services > 0:
            log(f"services already exist ({existing_services}); leaving "
                f"{len(menu_items)} menu_item(s) in place for manual review")
        else:
            log("no menu_items to convert")

        # 4) config: restaurant_configs -> typed config collection
        typed_cfg = await cfg_coll.find_one({"restaurant_id": rid}, {"_id": 0})
        if not typed_cfg:
            log(f"copy config restaurant_configs -> {CONFIG_COLL[btype]}")
            if COMMIT:
                await cfg_coll.insert_one({k: v for k, v in cfg.items() if k != "_id"})
                await db.restaurant_configs.delete_one({"restaurant_id": rid})
        else:
            log(f"typed config already present in {CONFIG_COLL[btype]}; "
                f"deleting stray restaurant_configs copy")
            if COMMIT:
                await db.restaurant_configs.delete_one({"restaurant_id": rid})

        print()

    print("Done." + ("" if COMMIT else "  (dry run — re-run with --commit to apply)"))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
