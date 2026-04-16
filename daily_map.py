import googlemaps
import folium
import requests
import re
import os
from icalendar import Calendar
from datetime import date, datetime

# --- CONFIGURATION ---
GOOGLE_MAPS_API_KEY = os.getenv('GMAPS_API_KEY')
BASE_ADDRESS = "Plaza Pedro Montt 4952, Ñuñoa, Santiago de Chile" 
CENTER_ADDRESS = "Avenida Francisco Bilbao 4173, La Reina, Santiago de Chile"

MECHANICS = {
    "Juan": "https://www.bookthatapp.com/ical/2NZIK6V9T86G4QN7/calendar.ics?resource=31043&token=7242fe38f484ff07e05e4d73fc92c8",
    "Seba": "https://www.bookthatapp.com/ical/2NZIK6V9T86G4QN7/calendar.ics?resource=34470&token=7242fe38f484ff07e05e4d73fc92c8"
}

MECH_COLORS = {
    "Juan": ['#3498db', '#2980b9', '#8e44ad', '#2c3e50'],
    "Seba": ['#e67e22', '#d35400', '#c0392b', '#f39c12']
}

gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def extract_customer_name(description):
    if not description: return "Customer"
    match = re.search(r"Cliente:\s*(.*?)\s*\(", str(description))
    return match.group(1).strip().upper() if match else "CUSTOMER"

def get_mechanic_data(name, url):
    print(f"Reading calendar for {name}...")
    try:
        response = requests.get(url.replace("webcal://", "https://"))
        gcal = Calendar.from_ical(response.content)
        today = date.today()
        appointments = []
        for component in gcal.walk():
            if component.name == "VEVENT":
                dt_start = component.get('dtstart').dt
                event_date = dt_start.date() if hasattr(dt_start, 'date') else dt_start
                if event_date == today:
                    appointments.append({
                        'time': dt_start,
                        'address': f"{component.get('summary')}, Santiago, Chile",
                        'name': extract_customer_name(component.get('description'))
                    })
        appointments.sort(key=lambda x: x['time'])
        return appointments
    except Exception as e:
        print(f"Error fetching {name}: {e}")
        return []

def create_map():
    print(f"Centering map on {CENTER_ADDRESS}...")
    center_geo = gmaps.geocode(CENTER_ADDRESS)[0]['geometry']['location']
    m = folium.Map(location=[center_geo['lat'], center_geo['lng']], zoom_start=13, tiles="cartodbpositron")

    for mech_name, url in MECHANICS.items():
        apps = get_mechanic_data(mech_name, url)
        if not apps: continue

        group = folium.FeatureGroup(name=mech_name, show=True)
        route_points = [BASE_ADDRESS] + [a['address'] for a in apps] + [BASE_ADDRESS]
        colors = MECH_COLORS.get(mech_name, ['#333333'])

        for i in range(len(route_points) - 1):
            color = colors[i % len(colors)]
            directions = gmaps.directions(route_points[i], route_points[i+1], mode="driving")
            
            if directions:
                leg_data = directions[0]['legs'][0]
                duration_text = leg_data['duration']['text']
                raw_points = googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])
                
                # Visual Offset: Juan shifts north, Seba shifts south
                offset = 0.00008 if mech_name == "Juan" else -0.00008
                coords = [(p['lat'] + offset, p['lng'] + offset) for p in raw_points]
                
                # 1. Draw Leg Route
                folium.PolyLine(coords, color=color, weight=6, opacity=0.8).add_to(group)
                
                # 2. Leg Time Label (Refined Styling)
                mid_p = coords[len(coords)//2]
                time_html = f"""
                    <div style="
                        background:{color}; 
                        color:white; 
                        border:2px solid white; 
                        padding:4px 10px; 
                        border-radius:15px; 
                        font-size:10pt; 
                        font-weight:bold; 
                        white-space:nowrap;
                        box-shadow: 2px 2px 5px rgba(0,0,0,0.4);
                        text-align:center;
                        display:inline-block;
                    ">
                        Leg {i+1}: {duration_text}
                    </div>"""
                folium.Marker(location=mid_p, icon=folium.DivIcon(html=time_html)).add_to(group)

                # 3. Customer Label
                if i < len(apps):
                    stop_lat = leg_data['end_location']['lat'] + offset
                    stop_lng = leg_data['end_location']['lng'] + offset
                    cust_name = apps[i]['name']
                    
                    cust_html = f"""
                        <div style="
                            background:white; 
                            color:#2c3e50; 
                            border:3px solid {color}; 
                            padding:4px 6px; 
                            font-size:8pt; 
                            font-weight:bold; 
                            min-width:70px; 
                            text-align:center; 
                            box-shadow:2px 2px 8px rgba(0,0,0,0.2);
                        ">
                            {cust_name} ({mech_name[0]})
                        </div>"""
                    folium.Marker(location=[stop_lat, stop_lng], icon=folium.DivIcon(html=cust_html)).add_to(group)

        group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # JavaScript for URL Parameters (?mechanic=Juan)
    custom_js = """
    <script>
    window.onload = function() {
        const urlParams = new URLSearchParams(window.location.search);
        const activeMech = urlParams.get('mechanic');
        if (activeMech) {
            document.querySelectorAll('.leaflet-control-layers-selector').forEach(el => {
                let label = el.nextSibling.innerText.trim();
                if (label !== activeMech && el.checked) {
                    el.click();
                }
            });
        }
    };
    </script>
    """
    m.get_root().html.add_child(folium.Element(custom_js))

    m.save("mechanic_route.html")
    print(f"\nSUCCESS: Map generated for {date.today()}.")

if __name__ == "__main__":
    create_map()