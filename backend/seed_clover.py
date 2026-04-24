"""
Seed Clover sandbox inventory from MongoDB menu items.
Usage: python seed_clover.py --restaurant-id <id>
"""
import asyncio
import argparse
import os
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

CLOVER_TOKEN = os.environ.get("CLOVER_API_TOKEN", "")
CLOVER_MID = os.environ.get("CLOVER_MERCHANT_ID", "")
CLOVER_ENV = os.environ.get("CLOVER_ENV", "sandbox")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ringai_db")

BASE_URL = "https://sandbox.dev.clover.com" if CLOVER_ENV == "sandbox" else "https://api.clover.com"
HEADERS = {"Authorization": f"Bearer {CLOVER_TOKEN}", "Content-Type": "application/json"}


async def get_or_create_category(client: httpx.AsyncClient, name: str) -> str:
    """Get existing category ID or create new one."""
    resp = await client.get(f"{BASE_URL}/v3/merchants/{CLOVER_MID}/categories", headers=HEADERS)
    if resp.status_code == 200:
        for cat in resp.json().get("elements", []):
            if cat["name"].lower() == name.lower():
                return cat["id"]
    # Create new category
    resp = await client.post(
        f"{BASE_URL}/v3/merchants/{CLOVER_MID}/categories",
        headers=HEADERS,
        json={"name": name}
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    return None


async def seed_clover(restaurant_id: str):
    client_db = AsyncIOMotorClient(MONGO_URL)
    db = client_db[DB_NAME]

    items = await db.menu_items.find(
        {"restaurant_id": restaurant_id, "available": True},
        {"_id": 0}
    ).to_list(500)

    if not items:
        print(f"No menu items found for restaurant {restaurant_id}")
        return

    print(f"Found {len(items)} menu items to seed")

    async with httpx.AsyncClient(timeout=10.0) as client:
        category_cache = {}
        seeded = 0
        failed = 0

        for item in items:
            cat_name = item.get("category", "Uncategorized")
            if cat_name not in category_cache:
                cat_id = await get_or_create_category(client, cat_name)
                category_cache[cat_name] = cat_id

            payload = {
                "name": item["name"],
                "price": item.get("price", 0),
                "available": True,
            }

            resp = await client.post(
                f"{BASE_URL}/v3/merchants/{CLOVER_MID}/items",
                headers=HEADERS,
                json=payload,
            )

            if resp.status_code in (200, 201):
                clover_item_id = resp.json().get("id")
                # Assign category
                cat_id = category_cache.get(cat_name)
                if cat_id and clover_item_id:
                    await client.post(
                        f"{BASE_URL}/v3/merchants/{CLOVER_MID}/category_items",
                        headers=HEADERS,
                        json={"elements": [{"item": {"id": clover_item_id}, "category": {"id": cat_id}}]}
                    )
                # Update pos_item_id in MongoDB
                await db.menu_items.update_one(
                    {"restaurant_id": restaurant_id, "name": item["name"]},
                    {"$set": {"pos_item_id": clover_item_id}}
                )
                print(f"✅ {item['name']} → {clover_item_id}")
                seeded += 1
            else:
                print(f"❌ Failed: {item['name']} — {resp.status_code} {resp.text}")
                failed += 1

    print(f"\nDone: {seeded} seeded, {failed} failed")
    client_db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restaurant-id", required=True)
    args = parser.parse_args()
    asyncio.run(seed_clover(args.restaurant_id))