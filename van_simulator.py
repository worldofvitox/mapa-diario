import time
import random
import requests

# ⚠️ PASTE YOUR FIREBASE URL HERE (KEEP /vans.json AT THE END!)
FIREBASE_URL = "https://vantracker-7cdef-default-rtdb.firebaseio.com/vans.json"

# Start the vans near Base
vans = {
    "Seba": {"lat": -33.45219, "lng": -70.57873},
    "Juan": {"lat": -33.45219, "lng": -70.57873}
}

print("🚐 Starting Live Van Simulator...")
print(f"📡 Broadcasting to: {FIREBASE_URL}\n")

while True:
    for mechanic, coords in vans.items():
        # "Drive" the vans a random distance (roughly 5-15 meters)
        coords["lat"] += random.uniform(-0.0002, 0.0002)
        coords["lng"] += random.uniform(-0.0002, 0.0002)

    try:
        # Push the new coordinates to Firebase
        response = requests.put(FIREBASE_URL, json=vans)
        print(f"✅ GPS Ping Sent! Seba: {vans['Seba']['lat']:.5f} | Juan: {vans['Juan']['lat']:.5f}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

    # Wait 5 seconds before the next GPS ping
    time.sleep(5)