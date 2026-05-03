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
import unicodedata
import urllib.parse

try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    pass

# ⚠️ PASTE YOUR FIREBASE URL HERE
FIREBASE_URL = 'https://vantracker-7cdef-default-rtdb.firebaseio.com/vans.json'

# ⚠️ GMAPS KEY
GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')

BASE_LOCATION = [-33.45219480797122, -70.5787333882418] 
CALENDAR_URL = 'https://calendar.google.com/calendar/ical/c_0e3e9c70ab1527edfef805c43e9fd06dabb0fdfab8e5081f4feb40565337708b%40group.calendar.google.com/private-a534c46e66604fef2e96a3dc4810f688/basic.ics'
CACHE_FILE = 'appointments_cache.json'
CONFIG_URL = 'https://docs.google.com/spreadsheets/d/1Sgtl_4Fm88-vVMfCrGxULl1Tg0ekD6rXT-P59hUlVSw/export?format=csv'

# Brand Colors
CHUM_BLUE = "#011E41"

MECHANICS = {
    'Juan': {'palette': ['#dc3545', '#c82333', '#a71d2a', '#e4606d', '#eb8c95'], 'initial': 'J', 'offset': (0.00012, 0.00012)},
    'Seba': {'palette': ['#007bff', '#0056b3', '#004085', '#3399ff', '#66b2ff'], 'initial': 'S', 'offset': (-0.00012, -0.00012)}
}

# Universal Brand Fonts CSS
BRAND_CSS = """
@font-face { font-family: 'Saturn-Bold'; src: url('Saturn-Bold.woff') format('woff'), url('Saturn-Bold.ttf') format('truetype'); }
@font-face { font-family: 'Gotham'; src: url('Gotham%20Book.otf') format('opentype'); font-weight: normal; }
@font-face { font-family: 'Gotham'; src: url('Gotham%20Bold.otf') format('opentype'); font-weight: bold; }
@font-face { font-family: 'Gotham'; src: url('Gotham%20Medium.otf') format('opentype'); font-weight: 500; }
body, html { font-family: Gotham, sans-serif; }
::placeholder { font-family: Gotham, sans-serif !important; opacity: 0.6; }
"""

CARD_STYLE = (
    "font-family: Gotham, sans-serif; font-size: 11px; font-weight: bold; "
    "background-color: white; padding: 5px 10px; border-radius: 8px; "
    "box-shadow: 0px 3px 8px rgba(0,0,0,0.15); white-space: nowrap; "
    "display: inline-flex; align-items: center; border: none;"
)

WAZE_ICON_URL = "waze.png" 
all_legs_data = []

def normalize_text(text):
    if not text: return ""
    text = str(text).lower().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def get_service_config():
    config = []
    try:
        response = requests.get(CONFIG_URL, timeout=10)
        if response.status_code == 200:
            lines = response.content.decode('utf-8').splitlines()
            reader = csv.reader(lines)
            headers = next(reader)
            
            abbr_idx, prod_idx, var_idx, comb_idx, short_idx, dur_idx = 0, 1, 2, 3, 4, 5
            for i, h in enumerate(headers):
                h_norm = normalize_text(h)
                if any(kw in h_norm for kw in ['abbreviation', 'abbrev', 'sigla']): abbr_idx = i
                elif any(kw in h_norm for kw in ['product title', 'producto']): prod_idx = i
                elif any(kw in h_norm for kw in ['variant', 'variante']): var_idx = i
                elif any(kw in h_norm for kw in ['combined', 'combinado']): comb_idx = i
                elif any(kw in h_norm for kw in ['shorthand', 'corto']): short_idx = i
                elif any(kw in h_norm for kw in ['duration', 'minutos', 'minutes']): dur_idx = i
            
            for row in reader:
                abbrev = row[abbr_idx].strip() if len(row) > abbr_idx else "SRV"
                prod = row[prod_idx].strip() if len(row) > prod_idx else ""
                var = row[var_idx].strip() if len(row) > var_idx else ""
                comb = row[comb_idx].strip() if len(row) > comb_idx else ""
                shorthand = row[short_idx].strip() if len(row) > short_idx else ""
                try: 
                    duration_str = row[dur_idx].strip() if len(row) > dur_idx else ""
                    duration = int(re.sub(r'\D', '', duration_str)) if duration_str else 60
                except: duration = 60
                
                config.append({
                    'abbrev': abbrev, 'prod': prod, 'var': var, 
                    'comb': comb, 'shorthand': shorthand, 'duration': duration
                })
    except: pass
    return config

GLOBAL_CONFIG = get_service_config()

def group_overlapping(items):
    clusters = []
    for item in items:
        placed = False
        for cluster in clusters:
            overlaps = False
            for c_item in cluster:
                if max(item['top'], c_item['top']) < min(item['top'] + item['height'], c_item['top'] + c_item['height']):
                    overlaps = True; break
            if overlaps:
                cluster.append(item)
                placed = True; break
        if not placed:
            clusters.append([item])
    return clusters

def apply_offset(points, offset_tuple, multiplier=1):
    return [(p[0] + (offset_tuple[0] * multiplier), p[1] + (offset_tuple[1] * multiplier)) for p in points]

def extract_var(text, key):
    pattern = rf'(?i){key}[:\s]*([^\n\r]+)'
    match = re.search(pattern, text)
    if match: 
        val = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        val = re.split(r'(?i)(Comuna:|Servicio:|Telefono:|Teléfono:|Booking:|Cliente:|Address1:|Address2:)', val)[0].strip()
        return val
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
                    
                    raw_notas = ""
                    notas_match = re.search(r'(?i)Notas?:(.*?)(?=Booking:|Telefono:|Teléfono:|Cliente:|Address1:|Address2:|Comuna:|Servicio:|$)', clean_desc, re.DOTALL | re.IGNORECASE)
                    if notas_match: raw_notas = notas_match.group(1).strip()
                    
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
                    
                    norm_servicio = normalize_text(servicio)
                    abbrev, duration, shorthand = "SRV", 60, servicio
                    match_found = False
                    
                    for row in sorted(GLOBAL_CONFIG, key=lambda x: len(x['comb']), reverse=True):
                        if row['comb'] and normalize_text(row['comb']) in norm_servicio:
                            abbrev, duration, shorthand = row['abbrev'], row['duration'], row['shorthand']; match_found = True; break
                    if not match_found:
                        for row in sorted(GLOBAL_CONFIG, key=lambda x: len(x['prod']), reverse=True):
                            if row['prod'] and normalize_text(row['prod']) in norm_servicio:
                                abbrev, duration, shorthand = row['abbrev'], row['duration'], row['shorthand']; match_found = True; break
                    if not match_found:
                        for row in sorted(GLOBAL_CONFIG, key=lambda x: len(x['var']), reverse=True):
                            if row['var'] and normalize_text(row['var']) in norm_servicio:
                                abbrev, duration, shorthand = row['abbrev'], row['duration'], row['shorthand']; break
                            
                    uid = booking_id if booking_id else f"{start_dt.timestamp()}_{mechanic_name}_{cliente}"
                    live_apps.append({
                        'uid': uid, 'booking_id': booking_id, 'name': cliente, 
                        'address1': address1, 'address2': address2, 'comuna': comuna,
                        'route_address': f"{address1}, {comuna}, Santiago, Chile".strip(', '),
                        'service': servicio, 'mechanic': mechanic_name, 
                        'start_dt': start_dt.isoformat(), 'start_timestamp': start_dt.timestamp(), 
                        'abbrev': abbrev, 'duration': duration, 'shorthand': shorthand, 'notas': raw_notas
                    })
    except Exception as e: print(f"Error fetching live ICS: {e}")

    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: cache = json.load(f)
        except: pass

    now_ts = datetime.now(timezone).timestamp()
    merged = {}
    for app in live_apps: merged[app['uid']] = app
    for uid, cached_app in cache.items():
        if uid not in merged and cached_app['start_timestamp'] < now_ts: merged[uid] = cached_app

    with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(merged, f, ensure_ascii=False, indent=2)

    final_apps = []
    for uid, app in merged.items():
        app['start_dt'] = datetime.fromisoformat(app['start_dt'])
        final_apps.append(app)
    return final_apps

def generate_desktop_map_for_date(target_date, prev_date, next_date, all_apps, now_dt):
    global all_legs_data
    date_str = target_date.strftime('%Y-%m-%d')
    display_date = target_date.strftime('%a, %d %b')
    day_apps = [a for a in all_apps if a['start_dt'].date() == target_date]
    
    m = folium.Map(location=BASE_LOCATION, zoom_start=12, tiles=None)
    m.get_root().header.add_child(folium.Element(f'<script src="https://maps.googleapis.com/maps/api/js?key={GMAPS_KEY}"></script>'))
    
    favicon_html = f"""
    <style>{BRAND_CSS}</style>
    <link rel="icon" type="image/x-icon" href="favicon.ico?v=2">
    <link rel="icon" type="image/png" sizes="32x32" href="favicon-32x32.png?v=2">
    <link rel="icon" type="image/png" sizes="16x16" href="favicon-16x16.png?v=2">
    <link rel="apple-touch-icon" href="apple-touch-icon.png?v=2">
    """
    m.get_root().header.add_child(folium.Element(favicon_html))

    folium.TileLayer('cartodbpositron', control=False).add_to(m)
    folium.Marker(location=BASE_LOCATION, icon=folium.CustomIcon('base_icon.png', icon_size=(28, 28))).add_to(m)
    map_var_name = m.get_name()
    
    all_points = [BASE_LOCATION]
    global_max_n = 1
    
    grid_lines_html = ""
    offset_mins = 9 * 60 + 30 
    for h in range(9, 19):
        top_px = ((h * 60) - offset_mins) * 1.5
        if top_px >= 0:
            grid_lines_html += f'<div style="position:absolute; top:{top_px}px; left:0; right:0; height:1px; background:#eaeaea; z-index:0;"></div>'
            grid_lines_html += f'<div style="position:absolute; top:{top_px+2}px; left:2px; font-size:9px; color:#aaa; z-index:0; user-select:none; font-family:Gotham; font-weight:bold;">{h:02d}:00</div>'
    
    mechanics_container_html = ""
    
    for name in ['Juan', 'Seba']:
        info = MECHANICS[name]
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = sorted([a for a in day_apps if a['mechanic'] == name], key=lambda x: x['start_dt'])
        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        ui_apps = []
        ui_transits = []
        
        for i, app in enumerate(mech_apps):
            label_id = f"{info['initial']}{i+1}"
            leg_color = info['palette'][i % len(info['palette'])]
            app['label_id'] = label_id
            app['leg_color'] = leg_color
            arrival_target = app['start_dt']
            
            minutes_from_start = ((arrival_target.hour * 60 + arrival_target.minute) - offset_mins)
            app['panel_top'] = max(0, minutes_from_start * 1.5)
            app['panel_height'] = app.get('duration', 60) * 1.5
            
            if arrival_target.date() > now_dt.date(): directions = gmaps.directions(current_loc, app['route_address'], mode="driving")
            elif arrival_target > now_dt: directions = gmaps.directions(current_loc, app['route_address'], mode="driving", arrival_time=arrival_target)
            else: directions = gmaps.directions(current_loc, app['route_address'], mode="driving", departure_time=now_dt)

            if directions:
                leg = directions[0]['legs'][0]
                dist_m = leg.get('distance', {}).get('value', 0)
                app['lat'] = leg['end_location']['lat']
                app['lng'] = leg['end_location']['lng']
                app['address'] = app['route_address']
                app['end_time_ts'] = (arrival_target + timedelta(minutes=app.get('duration', 60))).timestamp()
                
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
                pill_content = f'<span style="font-family:Gotham; font-weight:bold;">{label_id} / {app["start_dt"].strftime("%H:%M")} / {short_cust_name}</span> / <span style="font-family:Gotham; font-weight:normal;">{display_addr1}</span>'
                folium.Marker(location=end_pt, icon=folium.DivIcon(html=f'<div style="{CARD_STYLE} color:{CHUM_BLUE}; transform:translate(-10%, -50%); pointer-events:none;">{pill_content}</div>')).add_to(fg)

                current_loc = app['route_address']
            else:
                app['transit_mins'] = 0

            ui_apps.append({'top': app['panel_top'], 'height': app['panel_height'], 'app': app})
            t_height = max(15, app.get('transit_mins', 0)) * 1.5
            t_top = app['panel_top'] - t_height
            ui_transits.append({'top': t_top, 'height': t_height, 'mins': app.get('transit_mins', 0)})

        for i, app in enumerate(mech_apps):
            if i + 1 < len(mech_apps):
                app['next_lat'] = mech_apps[i+1].get('lat', BASE_LOCATION[0])
                app['next_lng'] = mech_apps[i+1].get('lng', BASE_LOCATION[1])
                app['next_start_ts'] = mech_apps[i+1]['start_dt'].timestamp()
                app['next_address'] = mech_apps[i+1]['route_address']
            else:
                app['next_lat'], app['next_lng'] = BASE_LOCATION[0], BASE_LOCATION[1]
                app['next_start_ts'] = (now_dt.replace(hour=19, minute=0, second=0)).timestamp()
                app['next_address'] = "Base"

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
                base_label = f"{info['initial']}{len(mech_apps) + 1}"
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:#8A9892; transform:translateY(-20px); font-family:Gotham, sans-serif;"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{base_label} / Base / {buffered_mins} min</div></a>''')).add_to(fg)

                base_transit_h = max(15, buffered_mins) * 1.5
                base_transit_top = mech_apps[-1]['panel_top'] + mech_apps[-1]['panel_height']
                ui_transits.append({'top': base_transit_top, 'height': base_transit_h, 'mins': buffered_mins})

        app_clusters = group_overlapping(ui_apps)
        trans_clusters = group_overlapping(ui_transits)
        
        for cluster in app_clusters:
            n = len(cluster)
            global_max_n = max(global_max_n, n)
            for j, item in enumerate(cluster): item['anim_class'] = f"fade-{n}-{j}" if n > 1 else ""
                
        for cluster in trans_clusters:
            n = len(cluster)
            global_max_n = max(global_max_n, n)
            for j, item in enumerate(cluster): item['anim_class'] = f"fade-{n}-{j}" if n > 1 else ""

        planner_html = f"""
        <div style="flex: 1; display: flex; flex-direction: column; border-right: 1px solid #ddd; min-width: 0;">
            <div style="background: {info['palette'][0]}; color: white; font-family:Gotham, sans-serif; font-size: 13px; font-weight: bold; text-align: center; height: 35px; box-sizing: border-box; flex-shrink: 0; display:flex; align-items:center; justify-content:center;">Ruta {name}</div>
            <div style="flex-grow: 1; overflow-y: auto; overflow-x: hidden; background: white; position: relative;">
                <div style="height: 810px; position: relative; width: 100%;">
                    {grid_lines_html}
                    <div class="current-time-line" style="position:absolute; left:0; right:0; height:2px; background:#dc3545; z-index:4; display:none; pointer-events:none;"></div>
        """

        for cluster in trans_clusters:
            for item in cluster:
                planner_html += f"""
                <div class="{item['anim_class']}" style="position: absolute; top: {item['top']}px; left: 1%; width: 9%; height: {item['height']}px; display: flex; align-items: flex-end; justify-content: center; z-index: 2; padding-bottom: 2px; box-sizing: border-box;">
                    <div style="background: #f8f9fa; border: 1px solid #ccc; border-radius: 5px; font-family:Gotham; font-weight:normal; font-size: 9px; color: #444; width: 100%; height: 100%; max-height: 25px; display: flex; align-items: center; justify-content: center; overflow: hidden;">{item['mins']}m</div>
                </div>
                """
            
        for cluster in app_clusters:
            for item in cluster:
                app = item['app']
                full_address = f"{app['address1']} {app['address2']} {app['comuna']}".strip()
                full_address = re.sub(r'\s+', ' ', full_address)
                encoded_notas = urllib.parse.quote(app.get('notas', '')).replace("'", "%27")
                
                raw_json = json.dumps({
                    'lat': app.get('lat', BASE_LOCATION[0]), 'lng': app.get('lng', BASE_LOCATION[1]),
                    'address': app.get('address', ''), 'end_time_ts': app.get('end_time_ts', 0),
                    'next_lat': app.get('next_lat', BASE_LOCATION[0]), 'next_lng': app.get('next_lng', BASE_LOCATION[1]),
                    'next_start_ts': app.get('next_start_ts', 0), 'next_address': app.get('next_address', 'Base')
                })
                app_data_json = urllib.parse.quote(raw_json).replace("'", "%27")
                
                planner_html += f"""
                <div class="{item['anim_class']}" style="position: absolute; top: {item['top']}px; left: 10%; width: 88%; height: {item['height']}px; padding: 2px; box-sizing: border-box; z-index: 3