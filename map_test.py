import googlemaps
from datetime import datetime

# 1. Paste your Google API Key here
GOOGLE_MAPS_API_KEY = 'AIzaSyDMi_wbYarCHOgAHMdgxHecbCihjhUv-Cs'

# 2. Setup the Google Maps client
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def test_geocoding(address_text):
    print(f"Searching for: {address_text}...")
    
    # 3. Ask Google for the coordinates
    # We add "Santiago, Chile" to ensure it looks in the right city
    full_address = f"{address_text}, Santiago, Chile"
    geocode_result = gmaps.geocode(full_address)

    if geocode_result:
        location = geocode_result[0]['geometry']['location']
        lat = location['lat']
        lng = location['lng']
        print(f"Success! Found at: Latitude {lat}, Longitude {lng}")
        return lat, lng
    else:
        print("Could not find address.")
        return None

# Test it with a real Santiago address
if __name__ == "__main__":
    test_geocoding("Palacio de La Moneda")