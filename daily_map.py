import os
import re
import requests
import googlemaps
import folium
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar

# --- 1. CONFIGURATION ---
GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')

# Precision Base Location
BASE_LOCATION = [-33.45219480797122, -70.5787333882418] 

MECHANICS = {
    'Juan': {
        'url': 'https://www.bookthatapp.com/ical/2NZIK6V9T86G4QN7/calendar.ics?resource=31043&token=7242fe38f484ff07e05e4d73fc92c8',
        'palette': ['#dc3545', '#fd7e14', '#e83e8c', '#6f42c1', '#b02a37'],
        'initial': 'J',
        'offset': (0.00012, 0.00012)
    },
    'Seba': {
        'url': 'https://www.bookthatapp.com/ical/2NZIK6V9T86G4QN7/calendar.ics?resource=34470&token=7242fe38f484ff07e05e4d73fc92c8',
        'palette': ['#007bff', '#28a745', '#17a2b8', '#20c997', '#004085'],
        'initial': 'S',
        'offset': (-0.00012, -0.00012)
    }
}

# --- 2. UNIFIED UI STYLE ---
CARD_STYLE = (
    "font-family: sans-serif; font-size: 12px; font-weight: bold; "
    "background-color: rgba(255, 255, 255, 0.95); padding: 6px 10px; "
    "border-radius: 8px; box-shadow: 0px 2px 8px rgba(0,0,0,0.15); "
    "white-space: nowrap; width: auto; display: inline-block; "
    "pointer-events: none; border: none;"
)

def apply_offset(points, offset_tuple, multiplier=1):
    return [(p[0] + (offset_tuple[0] * multiplier), p[1] + (offset_tuple[1] * multiplier)) for p in points]

def get_appointments():
    all_appointments = []
    today = datetime.now(timezone).date()
    for name, info in MECHANICS.items():
        url = info['url'].replace('webcal://', 'https://')
        try:
            response = requests.get(url, timeout=15)
            if response.status_code != 200: continue
            gcal = Calendar.from_ical(response.content)
            for component in gcal.walk():
                if component.name == "VEVENT":
                    start_dt = component.get('dtstart').dt
                    if isinstance(start_dt, datetime):
                        event_dt = start_dt.astimezone(timezone)
                        event_date = event_dt.date()
                        start_time_str = event_dt.strftime('%Y-%m-%d %H:%M')
                    else:
                        event_date = start_dt
                        start_time_str = f"{start_dt} 09:00"

                    if event_date == today:
                        summary = str(component.get('summary', ''))
                        desc = str(component.get('description', ''))
                        name_match = re.search(r'Cliente:\s*(.*?)\s*\(', desc)
                        extracted_name = name_match.group(1).strip() if name_match else summary.split(',')[0]
                        all_appointments.append({
                            'name': extracted_name, 'address': summary, 
                            'mechanic': name, 'start_time': start_time_str
                        })
        except Exception as e: print(f"Error: {e}")
    return all_appointments

def generate_map():
    appointments = get_appointments()
    if not appointments: return

    m = folium.Map(location=BASE_LOCATION, zoom_start=13, tiles='cartodbpositron')
    folium.Marker(location=BASE_LOCATION, icon=folium.Icon(color='black', icon='home')).add_to(m)
    now_dt = datetime.now(timezone)

    for name, info in MECHANICS.items():
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = sorted([a for a in appointments if a['mechanic'] == name], key=lambda x: x['start_time'])
        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        for i, app in enumerate(mech_apps):
            leg_color = info['palette'][i % len(info['palette'])]
            label_id = f"{info['initial']}{i+1}"
            start_dt = timezone.localize(datetime.strptime(app['start_time'], '%Y-%m-%d %H:%M'))
            dep_time = max(start_dt, now_dt)

            directions = gmaps.directions(current_loc, app['address'], mode="driving", departure_time=dep_time)
            if directions:
                leg = directions[0]['legs'][0]
                duration = leg.get('duration_in_traffic', leg['duration'])['text'].replace(' mins', ' min')
                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                points = apply_offset(raw_pts, info['offset'])
                folium.PolyLine(points, color=leg_color, weight=6, opacity=0.85).add_to(fg)

                # Transit Pill
                mid = points[len(points)//2]
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'<div style="{CARD_STYLE} color: {leg_color};">{label_id}: {duration}</div>')).add_to(fg)

                # Customer Pill
                end_pt = apply_offset([(leg['end_location']['lat'], leg['end_location']['lng'])], info['offset'])[0]
                folium.Marker(location=end_pt, icon=folium.DivIcon(html=f'<div style="{CARD_STYLE} color: black; transform: translate(-10%, -50%);">{start_dt.strftime("%H:%M")} {app["name"]} ({label_id})</div>')).add_to(fg)
                current_loc = app['address']

        # Return to Base
        if mech_apps:
            last_dt = timezone.localize(datetime.strptime(mech_apps[-1]['start_time'], '%Y-%m-%d %H:%M'))
            ret_time = max(last_dt + timedelta(hours=1.5), now_dt)
            back = gmaps.directions(current_loc, f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}", mode="driving", departure_time=ret_time)
            if back:
                leg = back[0]['legs'][0]
                dur = leg.get('duration_in_traffic', leg['duration'])['text'].replace(' mins', ' min')
                raw_back_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(back[0]['overview_polyline']['points'])]
                back_pts = apply_offset(raw_back_pts, info['offset'], multiplier=2.5)
                folium.PolyLine(back_pts, color='#6c757d', weight=3, dash_array='10', opacity=0.6).add_to(fg)
                
                mid_back = back_pts[len(back_pts)//2]
                folium.Marker(location=mid_back, icon=folium.DivIcon(html=f'<div style="{CARD_STYLE} color: #6c757d;">base: {dur}</div>')).add_to(fg)

    # COLLAPSED=FALSE is critical so the JS can see the labels
    folium.LayerControl(collapsed=False).add_to(m)

    # --- THE "MENU-CLICKER" JAVASCRIPT ---
    js_filter = """
    <script>
    function autoFilter() {
        const params = new URLSearchParams(window.location.search);
        const mech = params.get('mechanic');
        if (!mech) return;

        const target = mech.toLowerCase();
        const selectors = document.querySelectorAll('.leaflet-control-layers-selector');
        
        if (selectors.length === 0) {
            setTimeout(autoFilter, 300); // Retry if menu isn't built yet
            return;
        }

        selectors.forEach(input => {
            const labelText = input.nextElementSibling.innerText.trim().toLowerCase();
            // If the label is a mechanic but NOT the one we want, uncheck it
            if ((labelText === 'juan' || labelText === 'seba') && labelText !== target) {
                if (input.checked) {
                    input.click(); 
                }
            }
        });
    }
    window.addEventListener('load', autoFilter);
    </script>
    """
    m.get_root().html.add_child(folium.Element(js_filter))
    m.save("mechanic_route.html")

if __name__ == "__main__":
    generate_map()