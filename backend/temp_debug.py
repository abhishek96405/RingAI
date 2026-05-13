from dotenv import load_dotenv; from pathlib import Path; import os
from pymongo import MongoClient
from bson import ObjectId
load_dotenv(Path('.env'))
client = MongoClient(os.environ['MONGO_URL'])
db_name = os.environ.get('DB_NAME', 'ringai_db')
db = client[db_name]
print(f"Database: {db_name}")
print(f"Restaurant count: {db.restaurants.count_documents({})}")
r = db.restaurants.find_one({'name': 'Bawarchi'}, {'_id':1, 'name':1})
print(f"Bawarchi lookup by name: {r}")
r2 = db.restaurants.find_one({'_id': ObjectId('69b32ae89e854246503b9bfa')}, {'_id':1, 'name':1})
print(f"Bawarchi lookup by ObjectId: {r2}")
