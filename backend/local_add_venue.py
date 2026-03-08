from core.database import get_db, init_firebase

init_firebase()
db = get_db()
db.collection("venues").document("test-restaurant").set(
    {
        "name": "Test Restaurant",
        "owners": [],
        "employees": [],
        "invite_pins": {"1234": {"role": "owner", "expires_at": None}},
    }
)
print("Added dummy venue with PIN 1234")
