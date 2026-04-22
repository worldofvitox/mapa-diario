import os
import re
import requests
import googlemaps
import folium
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar
import locale
import csv
import json

try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    pass

GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')

BASE_LOCATION = [-33.45219480797122, -70.5787333882418] 
CALENDAR_URL = 'https://calendar.google.com/calendar/ical/c_0e3e9c70ab1527edfef805c43e9fd06dabb0fdfab8e5081f4feb40565337708b%40group.calendar.google.com/private-a534c46e66604fef2e96a3dc4810f688/basic.ics'
CACHE_FILE = 'appointments_cache.json'

MECHANICS = {
    'Juan': {'palette': ['#dc3545', '#fd7e14', '#e83e8c', '#6f42c1', '#b02a37'], 'initial': 'J', 'offset': (0.00012, 0.00012)},
    'Seba': {'palette': ['#007bff', '#28a745', '#17a2b8', '#20c997', '#004085'], 'initial': 'S', 'offset': (-0.00012, -0.00012)}
}

SERVICE_MAP = {
    "Armado de Bicicleta a Domicilio Con Cambios": "ARC", "Armado de Bicicleta a Domicilio Sin Cambios": "ARS",
    "Armado de Bicicleta a Domicilio Armado con Optimizado": "ARO", "Armado de Bicicleta a Domicilio Armado Bici Eléctrica Rigida": "ARE",
    "Armado de Bicicleta a Domicilio Con Retráctil y/o Bloqueo Remoto": "ARB", "Cambio de Juego de Dirección o Horquilla Cambio de Horquilla": "DIR",
    "Cambio de Juego de Dirección o Horquilla Cambio de Direccion": "DIR", "Cambio de Juego de Dirección o Horquilla Cambio de Direccion y Horquilla": "DIR",
    "Conversion a Tubeless 1 Rueda": "TUB", "Conversion a Tubeless Con Inserto / Cushcore": "TUB", "Conversion a Tubeless": "TUB",
    "Desenrayado y Enrayado de Rueda de Bicicleta": "DES", "Mantencion Clasica de Bicicleta Mant. Clasica 1 Bici": "CL1",
    "Mantencion Clasica de Bicicleta Mant. Clasica 2 Bicis": "CL2", "Mantencion Clasica de Bicicleta Mant. Clasica 3 Bicis": "CL3",
    "Mantencion Clasica de Bicicleta Mant. Clasica 4 Bicis": "CL4", "Mantencion Clasica de Bicicleta Mant. Clasica 5 Bicis": "CL5",
    "Mantencion Clasica de Bicicleta": "CL1", "Mantención de Bicicleta a Domicilio Mantencion Preventiva 1 Bici": "PR1",
    "Mantención de Bicicleta a Domicilio Mantencion Clasica 1 Bici": "CL1", "Mantención de Bicicleta a Domicilio Mantencion Profunda 1 Bici": "PF1",
    "Mantención de Bicicleta a Domicilio Mantencion Preventiva 2 Bicis": "PR2", "Mantención de Bicicleta a Domicilio Mantencion Clasica 2 Bicis": "CL2",
    "Mantención de Bicicleta a Domicilio Mantencion Preventiva 3 Bicis": "PR3", "Mantención de Bicicleta a Domicilio Mantencion Base Electrica": "ELR",
    "Mantención de Bicicleta a Domicilio Mantencion Base Ruta Aero / Triatlon": "TR1", "Mantención de Bicicleta a Domicilio Mantencion Profunda 2 Bicis": "PF2",
    "Mantención de Bicicleta a Domicilio Mantencion Clasica 3 Bicis": "CL3", "Mantención de Bicicleta a Domicilio Mantencion Profunda 3 Bicis": "PF3",
    "Mantención de Bicicleta Electrica Mant. Electrica Rigida": "ELR", "Mantención de Bicicleta Electrica Mant. Elect. Doble Susp.": "ELD",
    "Mantencion de Bicicleta Ruta Aero o de Triatlón 1 Bicicleta": "TR1", "Mantencion de Bicicleta Ruta Aero o de Triatlón 2 Bicicletas": "TR2",
    "Mantención Preventiva de Bicicletas Mant. Preventiva 1 Bici": "PR1", "Mantención Preventiva de Bicicletas Mant. Preventiva 2 Bicis": "PR2",
    "Mantención Preventiva de Bicicletas Mant. Preventiva 3 Bicis": "PR3", "Mantención Preventiva de Bicicletas Mant. Preventiva 4 Bicis": "PR4",
    "Mantención Preventiva de Bicicletas Mant. Preventiva 5 Bicis": "PR5", "Mantención Preventiva de Bicicletas": "PR1",
    "Mantencion Profunda de Bicicleta Mant. Profunda 1 Bici": "PF1", "Mantencion Profunda de Bicicleta Mant. Profunda 2 Bicis": "PF2",
    "Mantencion Profunda de Bicicleta Mant. Profunda 4 Bicis": "PF4", "Reparacion de Hilo (Inserto Helicoil)": "HEL",
    "Reparacion de Hilo de Cuadro/Horquilla (Rivnut)": "RIV", "Sangrado de Freno Hidráulico": "SAN",
    "Servicio de Amortiguador Trasero / Shock de aire": "SUR", "Servicio de Horquilla de Suspension": "SUF", "Visita Mecanica": "VM"
}

CARD_STYLE = (
    "font-family: 'Helvetica', sans-serif; font-size: 11px; font-weight: bold; "
    "background-color: white; padding: 5px 10px; border-radius: 8px; "
    "box-shadow: 0px 3px 8px rgba(0,0,0,0.15); white-space: nowrap; "
    "display: inline-flex; align-items: center; border: none;"
)

WAZE_ICON_URL = "waze.png" 
all_legs_data = []

def apply_offset(points, offset_tuple, multiplier=1):
    return [(p[0] + (offset_tuple[0] * multiplier), p[1] + (offset_tuple[1] * multiplier)) for p in points]

def extract_var(text, key):
    pattern = rf'(?i){key}[:\s]*([^\n\r]+)'
    match = re.search(pattern, text)
    if match: return re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return ""

def get_all_appointments():
    live_apps = []
    try:
        response = requests.get(CALENDAR_URL, timeout=15)
        if response.status_code == 200:
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
                    booking_id = extract_var(clean_desc, "Booking") 
                    
                    if not cliente:
                        name_match = re.search(r'Cliente:\s*(.*?)\s*\(', summary)
                        cliente = name_match.group(1).strip() if name_match else summary.split(',')[0]
                    if not address1:
                        parts = re.split(r'\s*\d+x\s+', summary, maxsplit=1, flags=re.IGNORECASE)
                        address1 = parts[0].strip().rstrip(',').strip()
                        if not servicio and len(parts) == 2: servicio = parts[1].strip()

                    desc_lower, sum_lower = clean_desc.lower(), summary.lower()
                    if "sebadechum" in desc_lower or "sebadechum" in sum_lower: mechanic_name = "Seba"
                    elif "juandechum" in desc_lower or "juandechum" in sum_lower: mechanic_name = "Juan"
                    else: continue
                    
                    abbrev = "SRV"
                    for key, code in sorted(SERVICE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
                        if key.lower() in servicio.lower():
                            abbrev = code
                            break
                    
                    uid = booking_id if booking_id else f"{start_dt.timestamp()}_{mechanic_name}_{cliente}"
                            
                    live_apps.append({
                        'uid': uid, 'booking_id': booking_id, 'name': cliente, 
                        'address1': address1, 'address2': address2, 'comuna': comuna,
                        'route_address': f"{address1}, {comuna}, Santiago, Chile".strip(', '),
                        'service': servicio, 'mechanic': mechanic_name, 
                        'start_dt': start_dt.isoformat(), 'start_timestamp': start_dt.timestamp(), 'abbrev': abbrev
                    })
    except Exception as e: print(f"Error fetching live ICS: {e}")

    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except: pass

    now_ts = datetime.now(timezone).timestamp()
    merged = {}

    for app in live_apps: merged[app['uid']] = app
    for uid, cached_app in cache.items():
        if uid not in merged:
            if cached_app['start_timestamp'] < now_ts:
                merged[uid] = cached_app

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    final_apps = []
    for uid, app in merged.items():
        app['start_dt'] = datetime.fromisoformat(app['start_dt'])
        final_apps.append(app)

    return final_apps

def generate_desktop_map_for_date(target_date, prev_date, next_date, all_apps, now_dt):
    global all_legs_data
    date_str = target_date.strftime('%Y-%m-%d')
    display_date = target_date.strftime('%a, %d %b').capitalize()
    
    day_apps = [a for a in all_apps if a['start_dt'].date() == target_date]
    
    m = folium.Map(location=BASE_LOCATION, zoom_start=12, tiles=None)
    folium.TileLayer('cartodbpositron', control=False).add_to(m)
    folium.Marker(location=BASE_LOCATION, icon=folium.Icon(color='black', icon='home')).add_to(m)
    
    all_points = [BASE_LOCATION]
    
    # Pre-build background grid (1 min = 1.5px -> 1 hour = 90px)
    grid_lines_html = ""
    for h in range(9, 19):
        top_px = (h - 9) * 90
        grid_lines_html += f'<div style="position:absolute; top:{top_px}px; left:0; right:0; height:1px; background:#eaeaea; z-index:0;"></div>'
        grid_lines_html += f'<div style="position:absolute; top:{top_px+2}px; left:2px; font-size:9px; color:#aaa; z-index:0; user-select:none;">{h:02d}:00</div>'
    
    mechanics_container_html = ""
    
    for name in ['Juan', 'Seba']:
        info = MECHANICS[name]
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = sorted([a for a in day_apps if a['mechanic'] == name], key=lambda x: x['start_dt'])
        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        # Calculate routing and prep UI data
        for i, app in enumerate(mech_apps):
            label_id = f"{info['initial']}{i+1}"
            leg_color = info['palette'][i % len(info['palette'])]
            app['label_id'] = label_id
            app['leg_color'] = leg_color
            
            arrival_target = app['start_dt']
            
            # Pre-calculate UI grid positions
            app['panel_top'] = max(0, ((arrival_target.hour - 9) * 60 + arrival_target.minute) * 1.5)
            
            if arrival_target.date() > now_dt.date(): directions = gmaps.directions(current_loc, app['route_address'], mode="driving")
            elif arrival_target > now_dt: directions = gmaps.directions(current_loc, app['route_address'], mode="driving", arrival_time=arrival_target)
            else: directions = gmaps.directions(current_loc, app['route_address'], mode="driving", departure_time=now_dt)

            if directions:
                leg = directions[0]['legs'][0]
                dist_m = leg.get('distance', {}).get('value', 0)
                
                all_legs_data.append({
                    'Date': date_str, 'Mechanic': name, 'ID': app.get('booking_id') or 'MANUAL',
                    'Client': app['name'], 'Type': 'Ruta a Cliente', 'Distance_km': round(dist_m / 1000, 2)
                })
                
                raw_seconds = leg.get('duration_in_traffic', leg['duration'])['value']
                penalty_seconds = 180 if app['address2'] else 0
                buffered_seconds = (raw_seconds * 1.07) + penalty_seconds
                buffered_mins = round(buffered_seconds / 60)
                app['transit_mins'] = buffered_mins
                
                departure_dt = arrival_target - timedelta(seconds=buffered_seconds)
                
                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                all_points.extend(raw_pts)
                points = apply_offset(raw_pts, info['offset'])
                folium.PolyLine(points, color=leg_color, weight=6, opacity=0.85).add_to(fg)

                mid = points[len(points)//2]
                waze_link = f"https://waze.com/ul?ll={leg['end_location']['lat']},{leg['end_location']['lng']}&navigate=yes"
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:{leg_color}; transform:translateY(-20px);"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{label_id} / {departure_dt.strftime('%H:%M')} / {buffered_mins} min</div></a>''')).add_to(fg)

                short_cust_name = app['name'][:20]
                display_addr1 = app['address1'][:20] + "..." if len(app['address1']) > 20 else app['address1']
                end_pt = apply_offset([(leg['end_location']['lat'], leg['end_location']['lng'])], info['offset'])[0]
                folium.Marker(location=end_pt, icon=folium.DivIcon(html=f'<div style="{CARD_STYLE} color:black; transform:translate(-10%, -50%); pointer-events:none;">{app["start_dt"].strftime("%H:%M")} / {short_cust_name} / {display_addr1} / {app["abbrev"]}</div>')).add_to(fg)

                current_loc = app['route_address']
            else:
                app['transit_mins'] = 0

        if mech_apps:
            base_str = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
            return_target = mech_apps[-1]['start_dt'] + timedelta(hours=1)
            
            if return_target.date() > now_dt.date(): directions = gmaps.directions(current_loc, base_str, mode="driving")
            elif return_target > now_dt: directions = gmaps.directions(current_loc, base_str, mode="driving", departure_time=return_target)
            else: directions = gmaps.directions(current_loc, base_str, mode="driving", departure_time=now_dt)

            if directions:
                leg = directions[0]['legs'][0]
                dist_m = leg.get('distance', {}).get('value', 0)
                
                all_legs_data.append({
                    'Date': date_str, 'Mechanic': name, 'ID': 'RETURN',
                    'Client': 'BASE', 'Type': 'Retorno a Base', 'Distance_km': round(dist_m / 1000, 2)
                })
                
                raw_seconds = leg.get('duration_in_traffic', leg['duration'])['value']
                buffered_mins = round((raw_seconds * 1.07) / 60)
                
                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                all_points.extend(raw_pts)
                points = apply_offset(raw_pts, info['offset'])
                
                folium.PolyLine(points, color=info['palette'][0], weight=5, opacity=0.6, dash_array='7, 7').add_to(fg)
                
                mid = points[len(points)//2]
                waze_link = f"https://waze.com/ul?ll={BASE_LOCATION[0]},{BASE_LOCATION[1]}&navigate=yes"
                
                # BUGFIX: Added + 1
                base_label = f"{info['initial']}{len(mech_apps) + 1}"
                
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:#666; transform:translateY(-20px);"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{base_label} / Base / {buffered_mins} min</div></a>''')).add_to(fg)

        # --- BUILD MECHANIC DAILY PLANNER HTML ---
        planner_html = f"""
        <div style="flex: 1; display: flex; flex-direction: column; border-right: 1px solid #ddd; min-width: 0;">
            <div style="background: {info['palette'][0]}; color: white; font-weight: bold; font-size: 13px; text-align: center; height: 35px; box-sizing: border-box; flex-shrink: 0; display:flex; align-items:center; justify-content:center;">Ruta {name}</div>
            <div style="flex-grow: 1; overflow-y: auto; overflow-x: hidden; background: white; position: relative;">
                <div style="height: 810px; position: relative; width: 100%;">
                    {grid_lines_html}
        """

        # Pre-cluster overlapping appointments (detects collisions within 90px/60min)
        clusters = []
        for app in mech_apps:
            if not clusters:
                clusters.append([app])
            else:
                if app['panel_top'] < clusters[-1][-1]['panel_top'] + 90:
                    clusters[-1].append(app)
                else:
                    clusters.append([app])

        # 1. Render Transit Pills (Left 10%)
        for i, app in enumerate(mech_apps):
            transit_top = max(0, app['panel_top'] - 45) if i == 0 else mech_apps[i-1]['panel_top'] + 90
            planner_html += f"""
            <div style="position: absolute; top: {transit_top}px; left: 1%; width: 10%; height: 45px; display: flex; align-items: center; justify-content: center; z-index: 2;">
                <div style="background: #f8f9fa; border: 1px solid #ccc; border-radius: 4px; font-size: 9px; color: #444; width: 100%; height: 80%; display: flex; align-items: center; justify-content: center; font-weight: bold;">{app.get('transit_mins', 0)}m</div>
            </div>
            """
            
        # 2. Render Panel Appointment Pills (Right 88%)
        for cluster in clusters:
            cols = len(cluster)
            width_pct = 88 / cols
            for j, app in enumerate(cluster):
                left_pct = 12 + (j * width_pct)
                full_address = f"{app['address1']} {app['address2']} {app['comuna']}".strip()
                full_address = re.sub(r'\s+', ' ', full_address)
                
                planner_html += f"""
                <div style="position: absolute; top: {app['panel_top']}px; left: {left_pct}%; width: {width_pct}%; height: 90px; padding: 2px; box-sizing: border-box; z-index: 3;">
                    <div style="background: white; border: 1px solid #ddd; border-radius: 15px 8px 8px 15px; height: 100%; display: flex; align-items: stretch; box-shadow: 0 2px 4px rgba(0,0,0,0.08); overflow: hidden;">
                        <div style="background: {app['leg_color']}; width: 30px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; flex-shrink: 0; font-size: 11px;">
                            {app['label_id']}
                        </div>
                        <div style="flex-grow: 1; padding: 5px 8px; display: flex; flex-direction: column; justify-content: center; overflow: hidden;">
                            <div style="font-weight: bold; font-size: 11px; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{app['start_dt'].strftime('%H:%M')} - {app['name']}</div>
                            <div style="font-size: 10px; color: #666; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin-top: 2px; line-height: 1.1;">{full_address}</div>
                        </div>
                        <div style="width: 25%; padding: 5px; display: flex; align-items: center; justify-content: center; text-align: center; font-size: 9px; font-weight: bold; color: #555; border-left: 1px dashed #eee; flex-shrink: 0;">
                            {app['service']}
                        </div>
                    </div>
                </div>
                """
                
        planner_html += "</div></div></div>"
        mechanics_container_html += planner_html

    folium.LayerControl(collapsed=False).add_to(m)
    if len(all_points) > 1: m.fit_bounds(all_points)

    carousel_html = f"""
    <div style="position: absolute; top: 15px; left: 60px; z-index: 9999; background: white; padding: 8px 20px; border-radius: 25px; box-shadow: 0 4px 10px rgba(0,0,0,0.15); display: flex; align-items: center; gap: 20px; font-family: sans-serif; font-weight: bold; font-size: 14px; border: 1px solid #eee;">
        <a href="desktop_map_{prev_date.strftime('%Y-%m-%d')}.html" style="text-decoration:none; color: #007bff; font-size: 18px; padding: 0 5px;">&lt;</a>
        <span style="color: #333; min-width: 120px; text-align: center;">{display_date}</span>
        <a href="desktop_map_{next_date.strftime('%Y-%m-%d')}.html" style="text-decoration:none; color: #007bff; font-size: 18px; padding: 0 5px;">&gt;</a>
    </div>
    """
    
    desktop_layout = f"""
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; overflow: hidden; background: #f4f6f8; font-family: sans-serif; }}
        .leaflet-container {{ width: 65vw !important; height: 100vh !important; position: absolute !important; left: 0 !important; top: 0 !important; }}
        .leaflet-control-layers-list::before {{ content: 'Ruta'; display: block; font-weight: bold; margin-bottom: 5px; border-bottom: 1px solid #ccc; padding-bottom: 3px; font-family: sans-serif;}}
        .leaflet-control-layers-base {{ display: none; }}
        
        /* Custom scrollbar for planner */
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-track {{ background: #f1f1f1; }}
        ::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #aaa; }}
    </style>
    
    <div id="desktop-side-panel" style="width: 35vw; height: 100vh; position: absolute; right: 0; top: 0; background: white; z-index: 9999; box-shadow: -4px 0 15px rgba(0,0,0,0.05); display: flex; flex-direction: column;">
        <div style="padding: 12px 15px; background: #343a40; color: white; font-size: 16px; font-weight: bold; flex-shrink: 0; text-align: center;">
            Planificación Diaria: {display_date}
        </div>
        <div style="display: flex; flex-direction: row; flex-grow: 1; overflow: hidden; width: 100%;">
            {mechanics_container_html}
        </div>
    </div>
    {carousel_html}
    """
    
    m.get_root().html.add_child(folium.Element(desktop_layout))
    m.save(f"desktop_map_{date_str}.html")

def update_distance_csv():
    file_name = 'distances.csv'
    historical_data = {}
    expected_fields = ['Date', 'Mechanic', 'ID', 'Client', 'Type', 'Distance_km']
    
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames and all(field in reader.fieldnames for field in expected_fields):
                    for row in reader:
                        key = f"{row['Date']}_{row['Mechanic']}_{row['ID']}_{row['Type']}"
                        historical_data[key] = row
        except Exception as e:
            print(f"Ignored old CSV format to prevent crash: {e}")
                
    for leg in all_legs_data:
        key = f"{leg['Date']}_{leg['Mechanic']}_{leg['ID']}_{leg['Type']}"
        historical_data[key] = leg
        
    with open(file_name, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=expected_fields)
        writer.writeheader()
        for key in sorted(historical_data.keys()):
            writer.writerow(historical_data[key])

if __name__ == "__main__":
    print("Fetching global appointments (with memory cache)...")
    all_apps = get_all_appointments()
    now_dt = datetime.now(timezone)
    
    if now_dt.hour >= 18: base_date = (now_dt + timedelta(days=1)).date()
    else: base_date = now_dt.date()

    days_to_generate = [-1, 0, 1, 2, 3, 4]
    for day_offset in days_to_generate:
        target = base_date + timedelta(days=day_offset)
        prev_d = target - timedelta(days=1)
        next_d = target + timedelta(days=1)
        generate_desktop_map_for_date(target, prev_d, next_d, all_apps, now_dt)
        
    update_distance_csv()
    
    with open("desktop_map.html", "w") as f:
        f.write(f'''
        <!DOCTYPE html>
        <html>
        <head><meta http-equiv="refresh" content="0; url=desktop_map_{base_date.strftime('%Y-%m-%d')}.html" /></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 20%; color: #666;">
            <h2>Cargando Centro de Control...</h2>
        </body>
        </html>
        ''')