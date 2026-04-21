import os
import re
import requests
import googlemaps
import folium
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar
import locale

# Try to set locale for Spanish dates, fallback to default if not available
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    pass

# --- CONFIGURATION ---
GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')

BASE_LOCATION = [-33.45219480797122, -70.5787333882418] 
CALENDAR_URL = 'https://calendar.google.com/calendar/ical/c_8opb357tnsp99elt8b7r9k79ss%40group.calendar.google.com/private-d744ba0d7a025c6d8b25c93752ed7cc1/basic.ics'

MECHANICS = {
    'Juan': {'palette': ['#dc3545', '#fd7e14', '#e83e8c', '#6f42c1', '#b02a37'], 'initial': 'J', 'offset': (0.00012, 0.00012)},
    'Seba': {'palette': ['#007bff', '#28a745', '#17a2b8', '#20c997', '#004085'], 'initial': 'S', 'offset': (-0.00012, -0.00012)}
}

# Condensed map for planning view
SERVICE_MAP = {
    "Armado": "ARM", "Tubeless": "TUB", "Mantencion Clasica": "CL1", 
    "Mantencion Preventiva": "PR1", "Mantencion Profunda": "PF1", 
    "Electrica": "ELR", "Ruta Aero": "TR1", "Visita Mecanica": "VM",
    "Juego de Dirección": "DIR", "Desenrayado": "DES", "Hilo": "HIL", "Sangrado": "SAN"
}

def apply_offset(points, offset_tuple, multiplier=1):
    return [(p[0] + (offset_tuple[0] * multiplier), p[1] + (offset_tuple[1] * multiplier)) for p in points]

def extract_var(text, key):
    pattern = rf'(?i){key}[:\s]*([^\n\r]+)'
    match = re.search(pattern, text)
    if match: return re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return ""

def get_all_appointments():
    """Fetches ALL appointments from the calendar at once to save bandwidth"""
    all_appointments = []
    try:
        response = requests.get(CALENDAR_URL, timeout=15)
        if response.status_code != 200: return []
        gcal = Calendar.from_ical(response.content)
        
        for component in gcal.walk():
            if component.name == "VEVENT":
                start_dt = component.get('dtstart').dt
                if not isinstance(start_dt, datetime):
                    start_dt = timezone.localize(datetime.combine(start_dt, datetime.min.time())).replace(hour=9)
                else:
                    start_dt = start_dt.astimezone(timezone)

                raw_desc = str(component.get('description', ''))
                summary = str(component.get('summary', ''))
                clean_desc = raw_desc.replace('\\n', '\n').replace('\\N', '\n').replace('&nbsp;', ' ')
                clean_desc = re.sub(r'<[^>]+>', '\n', clean_desc) 
                
                cliente = extract_var(clean_desc, "Cliente")
                address1 = extract_var(clean_desc, "Address1")
                address2 = extract_var(clean_desc, "Address2")
                comuna = extract_var(clean_desc, "Comuna")
                servicio = extract_var(clean_desc, "Servicio")
                
                if not cliente:
                    name_match = re.search(r'Cliente:\s*(.*?)\s*\(', summary)
                    cliente = name_match.group(1).strip() if name_match else summary.split(',')[0]
                if not address1:
                    parts = re.split(r'\s*\d+x\s+', summary, maxsplit=1, flags=re.IGNORECASE)
                    address1 = parts[0].strip().rstrip(',').strip()
                    if not servicio and len(parts) == 2: servicio = parts[1].strip()

                desc_lower, sum_lower = clean_desc.lower(), summary.lower()
                mechanic_name = "Seba" if "sebadechum" in desc_lower or "sebadechum" in sum_lower else ("Juan" if "juandechum" in desc_lower or "juandechum" in sum_lower else "Unassigned")
                
                abbrev = "SRV"
                for key, code in sorted(SERVICE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
                    if key.lower() in servicio.lower():
                        abbrev = code
                        break
                        
                all_appointments.append({
                    'name': cliente, 'address': f"{address1} {address2}".strip(),
                    'route_address': f"{address1}, {comuna}, Santiago, Chile",
                    'service': servicio, 'mechanic': mechanic_name, 
                    'start_dt': start_dt, 'abbrev': abbrev
                })
    except Exception as e: print(f"Error fetching: {e}")
    return all_appointments

def generate_desktop_map_for_date(target_date, prev_date, next_date, all_apps):
    date_str = target_date.strftime('%Y-%m-%d')
    display_date = target_date.strftime('%a, %d %b').capitalize()
    
    # Filter apps for this specific day
    day_apps = [a for a in all_apps if a['start_dt'].date() == target_date]
    
    m = folium.Map(location=BASE_LOCATION, zoom_start=12, tiles='cartodbpositron')
    folium.Marker(location=BASE_LOCATION, icon=folium.Icon(color='black', icon='home')).add_to(m)
    
    all_points = [BASE_LOCATION]
    side_panel_html = f"<div style='padding:15px; background:#343a40; color:white; font-size:18px; font-weight:bold;'>Planificación: {display_date}</div>"
    
    for name in ['Juan', 'Seba']:
        info = MECHANICS[name]
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = sorted([a for a in day_apps if a['mechanic'] == name], key=lambda x: x['start_dt'])
        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        if mech_apps:
            side_panel_html += f"<div style='padding:8px 15px; background:#e9ecef; border-bottom:2px solid {info['palette'][0]}; font-weight:bold; color:#333; margin-top:10px;'>Ruta {name}</div>"
            
        for i, app in enumerate(mech_apps):
            label_id = f"{info['initial']}{i+1}"
            leg_color = info['palette'][i % len(info['palette'])]
            
            # Simplified routing for planning view
            directions = gmaps.directions(current_loc, app['route_address'], mode="driving")
            
            if directions:
                leg = directions[0]['legs'][0]
                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                all_points.extend(raw_pts)
                points = apply_offset(raw_pts, info['offset'])
                folium.PolyLine(points, color=leg_color, weight=4, opacity=0.7).add_to(fg)

                dest = apply_offset([(leg['end_location']['lat'], leg['end_location']['lng'])], info['offset'])[0]
                
                # Planning Pill
                icon_html = f'''<div style="background:{leg_color}; color:white; border-radius:50%; width:24px; height:24px; display:flex; align-items:center; justify-content:center; font-weight:bold; border:2px solid white; box-shadow:0 2px 4px rgba(0,0,0,0.3); font-size:10px;">{label_id}</div>'''
                folium.Marker(location=dest, tooltip=f"{app['start_dt'].strftime('%H:%M')} | {app['name']}", icon=folium.DivIcon(html=icon_html)).add_to(fg)

                # Desktop Side Panel Card
                side_panel_html += f"""
                <div style="padding: 10px 15px; border-bottom: 1px solid #ddd; background: white; font-family: sans-serif; display: flex; align-items: center;">
                    <div style="background:{leg_color}; color:white; border-radius:50%; min-width:26px; height:26px; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:11px; margin-right:12px;">{label_id}</div>
                    <div style="flex-grow: 1;">
                        <div style="font-weight: bold; font-size: 13px; color: #333;">{app['start_dt'].strftime('%H:%M')} - {app['name'][:22]}</div>
                        <div style="font-size: 11px; color: #666; margin-top: 3px;">{app['address']}</div>
                        <div style="font-size: 10px; color: #888; margin-top: 2px;">{app['abbrev']} | {app['route_address'].split(',')[1].strip()}</div>
                    </div>
                </div>
                """
                current_loc = app['route_address']

    folium.LayerControl(collapsed=False).add_to(m)
    
    if len(all_points) > 1:
        m.fit_bounds(all_points)

    if len(day_apps) == 0:
        side_panel_html += "<div style='padding:20px; text-align:center; color:#888; font-family:sans-serif;'>No hay rutas programadas para este día.</div>"

    # --- DESKTOP UI INJECTION ---
    # 1. The Date Carousel (Floating on the map)
    carousel_html = f"""
    <div style="position: absolute; top: 15px; left: 60px; z-index: 9999; background: white; padding: 8px 20px; border-radius: 25px; box-shadow: 0 4px 10px rgba(0,0,0,0.15); display: flex; align-items: center; gap: 20px; font-family: sans-serif; font-weight: bold; font-size: 14px; border: 1px solid #eee;">
        <a href="desktop_map_{prev_date.strftime('%Y-%m-%d')}.html" style="text-decoration:none; color: #007bff; font-size: 18px; padding: 0 5px;">&lt;</a>
        <span style="color: #333; min-width: 120px; text-align: center;">{display_date}</span>
        <a href="desktop_map_{next_date.strftime('%Y-%m-%d')}.html" style="text-decoration:none; color: #007bff; font-size: 18px; padding: 0 5px;">&gt;</a>
    </div>
    """
    
    # 2. Layout CSS (70% Map, 30% Right Panel)
    desktop_layout = f"""
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; overflow: hidden; background: #f4f6f8; }}
        .leaflet-container {{ width: 70vw !important; height: 100vh !important; position: absolute !important; left: 0 !important; top: 0 !important; }}
    </style>
    <div id="desktop-side-panel" style="width: 30vw; height: 100vh; position: absolute; right: 0; top: 0; background: white; overflow-y: auto; border-left: 2px solid #ddd; z-index: 9999; box-shadow: -4px 0 15px rgba(0,0,0,0.05);">
        {side_panel_html}
    </div>
    {carousel_html}
    """
    
    m.get_root().html.add_child(folium.Element(desktop_layout))
    m.save(f"desktop_map_{date_str}.html")

if __name__ == "__main__":
    print("Fetching global appointments...")
    all_apps = get_all_appointments()
    
    now_dt = datetime.now(timezone)
    
    # "18:00 Rule" for Default Date
    if now_dt.hour >= 18:
        base_date = (now_dt + timedelta(days=1)).date()
    else:
        base_date = now_dt.date()
        
    print(f"Base logic date set to: {base_date}")

    # Generate a rolling 6-day window (Yesterday -> +4 Days)
    days_to_generate = [-1, 0, 1, 2, 3, 4]
    
    for day_offset in days_to_generate:
        target = base_date + timedelta(days=day_offset)
        prev_d = target - timedelta(days=1)
        next_d = target + timedelta(days=1)
        
        print(f"Generating Desktop View for: {target}")
        generate_desktop_map_for_date(target, prev_d, next_d, all_apps)
        
    # Generate the master "index" file that automatically redirects to the active base date
    with open("desktop_map.html", "w") as f:
        f.write(f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="refresh" content="0; url=desktop_map_{base_date.strftime('%Y-%m-%d')}.html" />
            <title>Cargando Dashboard...</title>
        </head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 20%; color: #666;">
            <h2>Cargando Centro de Control...</h2>
        </body>
        </html>
        ''')
    print("Desktop Map Generation Complete!")
