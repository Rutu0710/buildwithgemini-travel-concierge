import sys
import google.auth
from google.cloud import firestore

# Hardcoded project ID as required to ensure compatibility with local dev and deployed Agent Platform
PROJECT_ID = "qwiklabs-gcp-01-c3139008356e"

def get_firestore_client():
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return firestore.Client(project=PROJECT_ID, credentials=creds)
    except Exception:
        return firestore.Client(project=PROJECT_ID)

def seed_firestore():
    print(f"Connecting to Firestore with project ID: {PROJECT_ID}")
    db = get_firestore_client()
    collection_ref = db.collection("destinations")

    sample_destinations = [
        {
            "id": "tokyo-japan",
            "name": "Tokyo",
            "country": "Japan",
            "description": "Vibrant city with ancient temples, neon skyscrapers, and world-class food.",
            "price_per_night": 180,
            "rating": 4.9,
            "tags": ["culture", "city", "food"]
        },
        {
            "id": "paris-france",
            "name": "Paris",
            "country": "France",
            "description": "Romantic city of lights featuring iconic landmarks, art museums, and historic cafes.",
            "price_per_night": 220,
            "rating": 4.8,
            "tags": ["romance", "art", "city"]
        },
        {
            "id": "maui-hawaii",
            "name": "Maui",
            "country": "USA",
            "description": "Tropical paradise known for pristine beaches, volcanic landscapes, and surfing.",
            "price_per_night": 310,
            "rating": 4.9,
            "tags": ["beach", "nature", "relaxation"]
        },
        {
            "id": "kyoto-japan",
            "name": "Kyoto",
            "country": "Japan",
            "description": "Historic heart of Japan with serene gardens, traditional tea houses, and iconic shrines.",
            "price_per_night": 150,
            "rating": 4.9,
            "tags": ["culture", "nature", "history"]
        },
        {
            "id": "zurich-switzerland",
            "name": "Zurich",
            "country": "Switzerland",
            "description": "Picturesque alpine city surrounded by crystal lakes and breathtaking mountain views.",
            "price_per_night": 260,
            "rating": 4.7,
            "tags": ["mountains", "nature", "luxury"]
        }
    ]

    for item in sample_destinations:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        data = {k: v for k, v in item.items() if k != "id"}
        doc_ref.set(data)
        print(f"  [+] Seeded destination: {item['name']} ({doc_id})")

    print("Firestore seeding completed successfully!")

if __name__ == "__main__":
    seed_firestore()
