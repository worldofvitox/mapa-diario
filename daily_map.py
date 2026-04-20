import os
import re
import requests
import googlemaps
import folium
import urllib.parse
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar

# --- CONFIGURATION ---
GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')

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

CARD_STYLE = (
    "font-family: 'Helvetica', sans-serif; font-size: 11px; font-weight: bold; "
    "background-color: white; padding: 5px 10px; border-radius: 8px; "
    "box-shadow: 0px 3px 8px rgba(0,0,0,0.15); white-space: nowrap; "
    "display: inline-flex; align-items: center; border: none; text-decoration: none;"
)

WAZE_ICON_URL = "waze.png" 

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
                    else:
                        event_date = start_dt
                        event_dt = timezone.localize(datetime.combine(event_date, datetime.min.time())).replace(hour=9)

                    if event_date == today:
                        summary = str(component.get('summary', ''))
                        desc = str(component.get('description', ''))
                        name_match = re.search(r'Cliente:\s*(.*?)\s*\(', desc)
                        extracted_name = name_match.group(1).strip() if name_match else summary.split(',')[0]
                        all_appointments.append({
                            'name': extracted_name, 'address': summary, 
                            'mechanic': name, 'start_dt': event_dt
                        })
        except Exception as e: print(f"Error: {e}")
    return all_appointments

def generate_map():
    appointments = get_appointments()
    if not appointments: return

    # Use tiles=None and add TileLayer manually with control=False to remove the artifact
    m = folium.Map(location=BASE_LOCATION, zoom_start=13, tiles=None)
    folium.TileLayer('cartodbpositron', control=False).add_to(m)
    
    folium.Marker(location=BASE_LOCATION, icon=folium.Icon(color='black', icon='home')).add_to(m)
    now_dt = datetime.now(timezone)

    all_points_for_zoom = [BASE_LOCATION]

    for name, info in MECHANICS.items():
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = sorted([a for a in appointments if a['mechanic'] == name], key=lambda x: x['start_dt'])
        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        for i, app in enumerate(mech_apps):
            leg_color = info['palette'][i % len(info['palette'])]
            label_id = f"{info['initial']}{i+1}"
            arrival_target = app['start_dt']
            
            if arrival_target > now_dt:
                directions = gmaps.directions(current_loc, app['address'], mode="driving", arrival_time=arrival_target)
            else:
                directions = gmaps.directions(current_loc, app['address'], mode="driving", departure_time=now_dt)

            if directions:
                leg = directions[0]['legs'][0]
                
                # UPDATE 1: 7% Buffer
                raw_seconds = leg.get('duration_in_traffic', leg['duration'])['value']
                buffered_seconds = raw_seconds * 1.07 
                buffered_mins = round(buffered_seconds / 60)
                
                departure_dt = arrival_target - timedelta(seconds=buffered_seconds)
                dep_time_str = departure_dt.strftime('%H:%M')
                display_str = f"{label_id} / {dep_time_str} / {buffered_mins} min"

                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                all_points_for_zoom.extend(raw_pts)
                points = apply_offset(raw_pts, info['offset'])
                folium.PolyLine(points, color=leg_color, weight=6, opacity=0.85).add_to(fg)

                mid = points[len(points)//2]
                dest_lat, dest_lng = leg['end_location']['lat'], leg['end_location']['lng']
                waze_link = f"https://waze.com/ul?ll={dest_lat},{dest_lng}&navigate=yes"

                folium.Marker(
                    location=mid, 
                    icon=folium.DivIcon(html=f'''
                        <a href="{waze_link}" target="_blank" style="text-decoration: none; pointer-events: auto;">
                            <div style="{CARD_STYLE} color: {leg_color}; transform: translateY(-20px);">
                                <img src="{WAZE_ICON_URL}" style="width:16px; height:16px; margin-right:6px; vertical-align: middle;">
                                <span style="vertical-align: middle;">{display_str}</span>
                            </div>
                        </a>''')
                ).add_to(fg)

                end_pt = apply_offset([(dest_lat, dest_lng)], info['offset'])[0]
                folium.Marker(
                    location=end_pt, 
                    icon=folium.DivIcon(html=f'''
                        <div style="{CARD_STYLE} color: black; transform: translate(-10%, -50%); pointer-events: none;">
                            {app['start_dt'].strftime("%H:%M")} {app["name"]} ({label_id})
                        </div>''')
                ).add_to(fg)
                current_loc = app['address']

    # UPDATE 2: Add Title "Ruta" to Layer Control via CSS injection
    folium.LayerControl(collapsed=False).add_to(m)
    
    # UPDATE 3: Initial Zoom Logic (Fit Bounds with bottom padding)
    if all_points_for_zoom:
        lats = [p[0] for p in all_points_for_zoom]
        lngs = [p[1] for p in all_points_for_zoom]
        sw = [min(lats), min(lngs)]
        ne = [max(lats), max(lngs)]
        
        # To push the map into the top 75%, we create a "phantom" southwest point 
        # that extends far below the actual route.
        height = ne[0] - sw[0]
        sw_phantom = [sw[0] - (height * 0.4), sw[1]] 
        m.fit_bounds([sw_phantom, ne])

    # Injecting CSS to fix the Layer Control title and clean up the UI
    css_fix = """
    <style>
    .leaflet-control-layers-list::before {
        content: 'Ruta';
        display: block;
        font-family: 'Helvetica', sans-serif;
        font-weight: bold;
        font-size: 14px;
        margin-bottom: 5px;
        border-bottom: 1px solid #ccc;
        padding-bottom: 3px;
    }
    /* Hide the default empty space/artifact if any */
    .leaflet-control-layers-base { display: none; }
    </style>
    """
    
    # Auto-filter JS
    js_filter = """
    <script>
    function autoFilter() {
        const params = new URLSearchParams(window.location.search);
        const mech = params.get('mechanic');
        if (!mech) return;
        const target = mech.toLowerCase();
        const selectors = document.querySelectorAll('.leaflet-control-layers-selector');
        if (selectors.length === 0) { setTimeout(autoFilter, 300); return; }
        selectors.forEach(input => {
            const labelText = input.nextElementSibling.innerText.trim().toLowerCase();
            if ((labelText === 'juan' || labelText === 'seba') && labelText !== target) {
                if (input.checked) { input.click(); }
            }
        });
    }
    window.addEventListener('load', autoFilter);
    </script>
    """
    m.get_root().header.add_child(folium.Element(css_fix))
    m.get_root().html.add_child(folium.Element(js_filter))
    m.save("mechanic_route.html")

if __name__ == "__main__":
    generate_map()