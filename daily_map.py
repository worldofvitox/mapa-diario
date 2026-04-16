import os
import requests
import googlemaps
import folium
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar

# --- CONFIGURATION ---
GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')
BASE_LOCATION = [-33.4489, -70.6693] # Workshop

MECHANICS = {
    'Juan': {
        'url': 'https://www.bookthatapp.com/ical/2NZIK6V9T86G4QN7/calendar.ics?resource=31043&token=7242fe38f484ff07e05e4d73fc92c8',
        'color': '#dc3545',
        'initial': 'J'
    },
    'Seba': {
        'url': 'https://www.bookthatapp.com/ical/2NZIK6V9T86G4QN7/calendar.ics?resource=34470&token=7242fe38f484ff07e05e4d73fc92c8',
        'color': '#007bff',
        'initial': 'S'
    }
}

def get_appointments():
    """Fetches and parses iCal files from BookThatApp."""
    all_appointments = []
    today = datetime.now(timezone).date()

    for name, info in MECHANICS.items():
        # Change webcal:// to https:// so requests can handle it
        url = info['url'].replace('webcal://', 'https://')
        response = requests.get(url)
        
        if response.status_code != 200:
            print(f"Failed to fetch calendar for {name}")
            continue

        gcal = Calendar.from_ical(response.content)

        for component in gcal.walk():
            if component.name == "VEVENT":
                start_dt = component.get('dtstart').dt
                
                # Handle both date and datetime objects
                if isinstance(start_dt, datetime):
                    event_date = start_dt.astimezone(timezone).date()
                    start_time_str = start_dt.astimezone(timezone).strftime('%Y-%m-%d %H:%M')
                else:
                    event_date = start_dt
                    start_time_str = f"{start_dt} 09:00"

                # Only include events for TODAY
                if event_date == today:
                    summary = str(component.get('summary', 'No Name'))
                    location = str(component.get('location', summary))
                    
                    all_appointments.append({
                        'name': summary,
                        'address': location,
                        'mechanic': name,
                        'start_time': start_time_str
                    })
    return all_appointments

def generate_map():
    appointments = get_appointments()
    if not appointments:
        print("No appointments found for today in iCal.")
        return

    m = folium.Map(location=BASE_LOCATION, zoom_start=12, tiles='cartodbpositron')
    folium.Marker(location=BASE_LOCATION, popup="Workshop", icon=folium.Icon(color='black', icon='home')).add_to(m)
    now_dt = datetime.now(timezone)

    for name, info in MECHANICS.items():
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = [a for a in appointments if a['mechanic'] == name]
        mech_apps.sort(key=lambda x: x['start_time'])

        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        for i, app in enumerate(mech_apps):
            count = i + 1
            label_id = f"{info['initial']}{count}"
            start_dt = timezone.localize(datetime.strptime(app['start_time'], '%Y-%m-%d %H:%M'))
            time_str = start_dt.strftime('%H:%M')
            dep_time = max(start_dt, now_dt)

            directions = gmaps.directions(current_loc, app['address'], mode="driving", departure_time=dep_time)

            if directions:
                leg = directions[0]['legs'][0]
                duration = leg.get('duration_in_traffic', leg['duration'])['text'].replace(' mins', ' min')
                pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                
                # Draw Route
                folium.PolyLine(pts, color=info['color'], weight=5, opacity=0.8).add_to(fg)

                # Transit Label (S1: 15 min)
                mid = pts[len(pts)//2]
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'<div style="font-family: sans-serif; font-size: 11px; color: white; background-color: {info["color"]}; padding: 3px 7px; border-radius: 10px; border: 2px solid white; font-weight: bold; white-space: nowrap;">{label_id}: {duration}</div>')).add_to(fg)

                # Customer Name Label
                end_lat, end_lng = leg['end_location']['lat'], leg['end_location']['lng']
                folium.Marker(location=[end_lat, end_lng], icon=folium.DivIcon(html=f'<div style="font-family: sans-serif; font-size: 12px; color: black; font-weight: bold; text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff; width: 250px;">{time_str} {app["name"]} ({label_id})</div>')).add_to(fg)

                current_loc = app['address']

        # Return Leg
        if mech_apps:
            last_dt = timezone.localize(datetime.strptime(mech_apps[-1]['start_time'], '%Y-%m-%d %H:%M'))
            ret_time = max(last_dt + timedelta(hours=1.5), now_dt)
            back = gmaps.directions(current_loc, f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}", mode="driving", departure_time=ret_time)
            if back:
                leg = back[0]['legs'][0]
                dur = leg.get('duration_in_traffic', leg['duration'])['text'].replace(' mins', ' min')
                pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(back[0]['overview_polyline']['points'])]
                folium.PolyLine(pts, color=info['color'], weight=3, dash_array='10', opacity=0.6).add_to(fg)
                mid = pts[len(pts)//2]
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'<div style="font-size: 10px; color: #666; background: white; padding: 2px; border: 1px solid #666;">base: {dur}</div>')).add_to(fg)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save("mechanic_route.html")

if __name__ == "__main__":
    generate_map()