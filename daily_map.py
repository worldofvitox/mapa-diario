import os
import googlemaps
import folium
from datetime import datetime, timedelta
import pytz

# --- CONFIGURATION ---
API_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=API_KEY)
timezone = pytz.timezone('America/Santiago')

# Coordinates for the "Base" (MBS Workshop)
BASE_LOCATION = "-33.4489, -70.6693" 

# Mechanics and their colors
MECHANICS = {
    'Seba': {'color': 'blue', 'initial': 'S'},
    'Juan': {'color': 'red', 'initial': 'J'}
}

def get_appointments():
    """
    Simulated function: In your real version, this fetches from BookThatApp.
    I'm including 'start_time' now for traffic and labels.
    """
    today = datetime.now(timezone).strftime('%Y-%m-%d')
    return [
        {'name': 'Cliente Alfa', 'address': 'Las Condes, Chile', 'mechanic': 'Seba', 'start_time': f'{today} 09:00'},
        {'name': 'Cliente Beta', 'address': 'Providencia, Chile', 'mechanic': 'Seba', 'start_time': f'{today} 11:30'},
        {'name': 'Cliente Gamma', 'address': 'Vitacura, Chile', 'mechanic': 'Juan', 'start_time': f'{today} 10:00'},
    ]

def generate_map():
    appointments = get_appointments()
    m = folium.Map(location=[-33.4489, -70.6693], zoom_start=12)

    for name, info in MECHANICS.items():
        # 1. Filter and sort appointments by time for this mechanic
        mech_apps = [a for a in appointments if a['mechanic'] == name]
        mech_apps.sort(key=lambda x: x['start_time'])

        current_loc = BASE_LOCATION
        
        for i, app in enumerate(mech_apps):
            count = i + 1
            label_id = f"{info['initial']}{count}" # e.g., S1, S2
            start_dt = datetime.strptime(app['start_time'], '%Y-%m-%d %H:%M')
            start_dt = timezone.localize(start_dt)
            time_str = start_dt.strftime('%H:%M')

            # 2. Get Directions with Traffic
            # We set departure_time to get duration_in_traffic
            directions = gmaps.directions(
                current_loc,
                app['address'],
                mode="driving",
                departure_time=start_dt, # Uses actual scheduled time for traffic
                traffic_model="best_guess"
            )

            if directions:
                leg = directions[0]['legs'][0]
                # Use duration_in_traffic if available, else standard duration
                duration = leg.get('duration_in_traffic', leg['duration'])['text'].replace(' mins', ' min')
                points = googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])
                
                # Draw the Line
                folium.PolyLine(points, color=info['color'], weight=5, opacity=0.7).add_to(m)

                # 3. Leg Marker (e.g., S1: 22 min)
                midpoint = points[len(points)//2]
                folium.Marker(
                    location=midpoint,
                    icon=folium.DivIcon(html=f'<div style="font-size: 10pt; color: {info['color']}; font-weight: bold; background: white; border: 1px solid black; border-radius: 5px; padding: 2px;">{label_id}: {duration}</div>')
                ).add_to(m)

                # 4. Customer Marker (e.g., 09:00 Cliente Alfa (S1))
                folium.Marker(
                    location=[leg['end_location']['lat'], leg['end_location']['lng']],
                    popup=f"{time_str} - {app['name']}",
                    tooltip=f"{time_str} {app['name']} ({label_id})",
                    icon=folium.Icon(color=info['color'], icon='info-sign')
                ).add_to(m)

                current_loc = app['address']

        # 5. Final Leg back to Base
        if mech_apps:
            # Estimate return time (Start of last job + 1.5 hours)
            last_start = datetime.strptime(mech_apps[-1]['start_time'], '%Y-%m-%d %H:%M')
            return_time = timezone.localize(last_start) + timedelta(hours=1.5)
            
            back_to_base = gmaps.directions(
                current_loc, BASE_LOCATION, 
                mode="driving", 
                departure_time=return_time
            )
            
            if back_to_base:
                leg = back_to_base[0]['legs'][0]
                duration = leg.get('duration_in_traffic', leg['duration'])['text'].replace(' mins', ' min')
                points = googlemaps.convert.decode_polyline(back_to_base[0]['overview_polyline']['points'])
                folium.PolyLine(points, color=info['color'], weight=3, dash_array='10', opacity=0.5).add_to(m)
                
                # Leg Label: base: 15 min
                midpoint = points[len(points)//2]
                folium.Marker(
                    location=midpoint,
                    icon=folium.DivIcon(html=f'<div style="font-size: 10pt; color: gray; font-weight: bold; background: white; border: 1px solid gray; border-radius: 5px; padding: 2px;">base: {duration}</div>')
                ).add_to(m)

    m.save("mechanic_route.html")

if __name__ == "__main__":
    generate_map()