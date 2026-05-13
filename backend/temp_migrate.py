from dotenv import load_dotenv; from pathlib import Path; import os, stripe
from pymongo import MongoClient
from bson import ObjectId
load_dotenv(Path('.env'))
stripe.api_key = os.environ['STRIPE_SECRET_KEY']
client = MongoClient(os.environ['MONGO_URL'])
db = client[os.environ.get('DB_NAME', 'ringai_db')]

clients = [
    {'oid': '69b32ae89e854246503b9bfa', 'name': 'Bawarchi', 'cust': 'cus_UUH8KqdMBQMvVc', 'sub': 'sub_1TVIdJ2VfI0U2XaQARx0Dmqk', 'email': 'dharmapuriabhishek02@gmail.com'},
    {'oid': '69c2e6f9525f31d5f448ed14', 'name': 'Desi Chowrastha', 'cust': 'cus_UUH837SNOsvsTR', 'sub': 'sub_1TVIdK2VfI0U2XaQxJU26ttM', 'email': 'dharmapuriabhishek03@gmail.com'},
]

for c in clients:
    s = stripe.Subscription.retrieve(c['sub'])
    print(f"{c['name']}: Stripe status = {s.status}")
    onboarding = ObjectId(c['oid']).generation_time.isoformat()
    result = db.restaurants.update_one(
        {'_id': ObjectId(c['oid'])},
        {'$set': {
            'stripe_customer_id': c['cust'],
            'stripe_subscription_id': c['sub'],
            'plan': 'PRO',
            'billing_status': s.status,
            'monthly_call_limit': 1000,
            'subscription_started_at': onboarding,
            'owner_email': c['email'],
        }}
    )
    print(f"  MongoDB updated: matched={result.matched_count}, modified={result.modified_count}")

print('\nVerifying...')
for c in clients:
    r = db.restaurants.find_one({'_id': ObjectId(c['oid'])}, {'name':1,'plan':1,'billing_status':1,'stripe_customer_id':1,'stripe_subscription_id':1,'monthly_call_limit':1,'monthly_call_count':1})
    print(f"\n{r['name']}:")
    for k,v in r.items():
        if k != '_id': print(f"  {k}: {v}")
