"""
fix_webhook_events_index.py

One-off repair for the webhook_events idempotency index.

Startup logs show code 86 (IndexKeySpecsConflict): the existing index
'provider_1_event_id_1' on {provider:1, event_id:1} is NON-unique, but the app
wants it UNIQUE. Mongo can't change an index's options in place under the same
name, so the app's ensure-index call fails every boot and webhook dedupe
(Stripe/Telnyx) is NOT enforced at the DB layer. If duplicate (provider,
event_id) rows already exist, recreating the index unique would fail with
E11000 -- hence the "manual dedupe" note.

This script, in order:
  1. checks the current index; exits early if it's already unique
  2. finds duplicate (provider, event_id) groups, keeps one doc per group
     (lowest _id), deletes the rest
  3. drops the stale non-unique 'provider_1_event_id_1'
  4. recreates it UNIQUE with the same name, so the app's startup ensure-index
     call becomes a no-op instead of erroring
  5. prints the resulting index list

Only the 'provider_1_event_id_1' index is ever touched; the TTL index on
webhook_events is left alone.

DRY-RUN by default. Re-run with --commit to apply. Idempotent.

Run (Render Shell, same as migrate_split_brain.py):
    python fix_webhook_events_index.py            # dry run
    python fix_webhook_events_index.py --commit   # apply
"""

import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

COLL = "webhook_events"
INDEX_NAME = "provider_1_event_id_1"
INDEX_KEYS = [("provider", 1), ("event_id", 1)]

COMMIT = "--commit" in sys.argv


def log(msg):
    prefix = "APPLY " if COMMIT else "DRYRUN"
    print(f"[{prefix}] {msg}")


async def main():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ringai_db")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    coll = db[COLL]

    print(f"Connected to {db_name}.{COLL}. Mode: {'COMMIT' if COMMIT else 'DRY RUN'}\n")

    # ---- 1) inspect current index ----------------------------------------
    info = await coll.index_information()
    cur = info.get(INDEX_NAME)
    if cur is not None and cur.get("unique", False):
        print(f"Index {INDEX_NAME!r} is already UNIQUE -- nothing to do.")
        client.close()
        return
    if cur is not None:
        print(f"Index {INDEX_NAME!r} exists and is NON-unique -- will rebuild as unique.")
    else:
        print(f"Index {INDEX_NAME!r} not present -- will create as unique.")

    # ---- 2) find + remove duplicate (provider, event_id) rows ------------
    pipeline = [
        {"$group": {
            "_id": {"provider": "$provider", "event_id": "$event_id"},
            "ids": {"$push": "$_id"},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    dup_groups = await coll.aggregate(pipeline).to_list(None)
    total_dupes = sum(g["count"] - 1 for g in dup_groups)

    if dup_groups:
        print(f"\nFound {len(dup_groups)} duplicated key(s), "
              f"{total_dupes} redundant doc(s) to delete:")
        for g in dup_groups:
            k = g["_id"]
            print(f"  provider={k.get('provider')!r} event_id={k.get('event_id')!r}  x{g['count']}")
        for g in dup_groups:
            ids = sorted(g["ids"])          # ObjectId sorts oldest-first
            keep, drop = ids[0], ids[1:]
            if COMMIT:
                res = await coll.delete_many({"_id": {"$in": drop}})
                log(f"kept {keep}, deleted {res.deleted_count} dup(s) for "
                    f"{g['_id'].get('provider')!r}/{g['_id'].get('event_id')!r}")
            else:
                log(f"would keep {keep}, delete {len(drop)} dup(s) for "
                    f"{g['_id'].get('provider')!r}/{g['_id'].get('event_id')!r}")
    else:
        print("\nNo duplicate (provider, event_id) rows. Unique index will build cleanly.")

    # ---- 3) drop the stale non-unique index ------------------------------
    if cur is not None:
        log(f"drop non-unique index {INDEX_NAME!r}")
        if COMMIT:
            await coll.drop_index(INDEX_NAME)

    # ---- 4) recreate as UNIQUE -------------------------------------------
    log(f"create UNIQUE index {INDEX_NAME!r} on {INDEX_KEYS}")
    if COMMIT:
        try:
            await coll.create_index(INDEX_KEYS, unique=True, name=INDEX_NAME)
        except OperationFailure as e:
            print(f"\nERROR creating unique index: {e}")
            print("Duplicates likely remain -- review and re-run.")
            client.close()
            return

    # ---- 5) confirm ------------------------------------------------------
    if COMMIT:
        final = await coll.index_information()
        print("\nIndexes now:")
        for name, spec in final.items():
            print(f"  {name}: key={spec.get('key')} unique={spec.get('unique', False)}")

    print("\nDone." + ("" if COMMIT else "  (dry run -- re-run with --commit to apply)"))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())