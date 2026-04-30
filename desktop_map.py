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
@font-face { font-family: 'Gotham'; src: url('Gotham Book.otf') format('opentype'); font-weight: normal; }
@font-face { font-family: 'Gotham'; src: url('Gotham Bold.otf') format('opentype'); font-weight: bold; }
@font-face { font-family: 'Gotham'; src: url('Gotham Medium.otf') format('opentype'); font-weight: 500; }
body, html { font-family: 'Gotham', sans-serif; }
"""

CARD_STYLE = (
    "font-family: 'Gotham', sans-serif; font-size: 11px; font-weight: bold; "
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
    display_date = target_date.strftime('%a, %d %b').capitalize()
    day_apps = [a for a in all_apps if a['start_dt'].date() == target_date]
    
    m = folium.Map(location=BASE_LOCATION, zoom_start=12, tiles=None)
    m.get_root().header.add_child(folium.Element(f'<script src="https://maps.googleapis.com/maps/api/js?key={GMAPS_KEY}"></script>'))
    
    favicon_html = """
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
            grid_lines_html += f'<div style="position:absolute; top:{top_px+2}px; left:2px; font-size:9px; color:#aaa; z-index:0; user-select:none; font-family:\'Gotham\'; font-weight:bold;">{h:02d}:00</div>'
    
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
                pill_content = f'{label_id} / {app["start_dt"].strftime("%H:%M")} / {short_cust_name} / {display_addr1}'
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
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:#8A9892; transform:translateY(-20px);"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{base_label} / Base / {buffered_mins} min</div></a>''')).add_to(fg)

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
            <div style="background: {info['palette'][0]}; color: white; font-family:'Saturn-Bold', sans-serif; font-size: 13px; text-align: center; height: 35px; box-sizing: border-box; flex-shrink: 0; display:flex; align-items:center; justify-content:center;">Ruta {name}</div>
            <div style="flex-grow: 1; overflow-y: auto; overflow-x: hidden; background: white; position: relative;">
                <div style="height: 810px; position: relative; width: 100%;">
                    {grid_lines_html}
                    <div class="current-time-line" style="position:absolute; left:0; right:0; height:2px; background:#dc3545; z-index:4; display:none; pointer-events:none;"></div>
        """

        for cluster in trans_clusters:
            for item in cluster:
                planner_html += f"""
                <div class="{item['anim_class']}" style="position: absolute; top: {item['top']}px; left: 1%; width: 9%; height: {item['height']}px; display: flex; align-items: flex-end; justify-content: center; z-index: 2; padding-bottom: 2px; box-sizing: border-box;">
                    <div style="background: #f8f9fa; border: 1px solid #ccc; border-radius: 5px; font-family:'Gotham'; font-size: 9px; color: #444; width: 100%; height: 100%; max-height: 25px; display: flex; align-items: center; justify-content: center; font-weight: bold; overflow: hidden;">{item['mins']}m</div>
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
                <div class="{item['anim_class']}" style="position: absolute; top: {item['top']}px; left: 10%; width: 88%; height: {item['height']}px; padding: 2px; box-sizing: border-box; z-index: 3; cursor: pointer; font-family:'Gotham';">
                    <div style="background: white; border: 1px solid #ddd; border-radius: 20px 10px 10px 20px; height: 100%; display: flex; align-items: stretch; box-shadow: 0 2px 4px rgba(0,0,0,0.08); overflow: hidden;">
                        <div onclick="showNotes(decodeURIComponent('{encoded_notas}'))" style="background: {app['leg_color']}; width: 30px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; flex-shrink: 0; font-size: 11px;">
                            {app['label_id']}
                        </div>
                        <div onclick="openDraftModal('{app_data_json}')" style="flex-grow: 1; padding: 5px 8px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; white-space: normal; word-wrap: break-word;">
                            <div style="font-weight: bold; font-size: 11px; color: {CHUM_BLUE};">{app['start_dt'].strftime('%H:%M')} - {app['name']}</div>
                            <div style="font-size: 10px; color: #8A9892; margin-top: 2px; line-height: 1.1;">{full_address}</div>
                        </div>
                        <div style="width: 25%; padding: 5px; display: flex; align-items: center; justify-content: center; text-align: center; font-size: 9px; font-weight: bold; color: {CHUM_BLUE}; border-left: 1px dashed #eee; flex-shrink: 0;">
                            {app['shorthand']}
                        </div>
                    </div>
                </div>
                """
                
        planner_html += "</div></div></div>"
        mechanics_container_html += planner_html

    folium.LayerControl(collapsed=False).add_to(m)
    if len(all_points) > 1: m.fit_bounds(all_points)

    anim_css = ""
    for n in range(2, global_max_n + 1):
        anim_css += f"@keyframes fade{n} {{\n"
        visible_pct = (1.0 / n) * 100
        anim_css += f"  0%, {max(0, visible_pct - 5)}% {{ opacity: 1; z-index: 10; }}\n"
        anim_css += f"  {visible_pct}%, {100 - (5.0/n)}% {{ opacity: 0; z-index: 1; }}\n"
        anim_css += f"  100% {{ opacity: 1; z-index: 10; }}\n  }}\n"
        for j in range(n):
            anim_css += f".fade-{n}-{j} {{ animation: fade{n} {n*3}s infinite; animation-delay: {j*3}s; opacity: 0; }}\n"

    carousel_html = f"""
    <div style="position: absolute; top: 15px; left: 60px; z-index: 9999; background: white; padding: 8px 20px; border-radius: 25px; box-shadow: 0 4px 10px rgba(0,0,0,0.15); display: flex; align-items: center; gap: 20px; border: 2px solid {CHUM_BLUE};">
        <a href="desktop_map_{prev_date.strftime('%Y-%m-%d')}.html" style="text-decoration:none; color: {CHUM_BLUE}; font-size: 18px; padding: 0 5px; font-weight:bold;">&lt;</a>
        <span style="color: {CHUM_BLUE}; font-family:'Saturn-Bold'; min-width: 120px; text-align: center;">{display_date}</span>
        <a href="desktop_map_{next_date.strftime('%Y-%m-%d')}.html" style="text-decoration:none; color: {CHUM_BLUE}; font-size: 18px; padding: 0 5px; font-weight:bold;">&gt;</a>
    </div>
    """
    
    modal_html = """
    <div id="notes-backdrop" onclick="closeNotes()" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(1,30,65,0.4); z-index:100000;"></div>
    <div id="notes-modal" onclick="event.stopPropagation()" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); background:white; padding:20px; border-radius:8px; box-shadow:0px 4px 15px rgba(0,0,0,0.3); z-index:100001; min-width:300px; max-width:80%; max-height:80vh; overflow-y:auto; font-family:'Gotham', sans-serif; font-size:14px; font-weight:normal; color:#011E41; border: 2px solid #011E41;">
        <div style="margin-bottom: 10px; font-size: 11px; color: #8A9892; text-transform: uppercase; font-family:'Saturn-Bold';">Notas de la Cita</div>
        <div id="notes-content" style="user-select:text; white-space: pre-wrap; line-height: 1.4;"></div>
        <div style="margin-top: 15px; text-align: right;">
            <button onclick="closeNotes()" style="background:#011E41; color:white; border:none; padding:5px 15px; border-radius:4px; cursor:pointer; font-weight:bold; font-family:'Gotham';">Cerrar</button>
        </div>
    </div>
    <script>
        function showNotes(text) {
            if(!text || text.trim() === '') text = 'Sin notas para esta cita.';
            document.getElementById('notes-content').textContent = text;
            document.getElementById('notes-backdrop').style.display = 'block';
            document.getElementById('notes-modal').style.display = 'block';
        }
        function closeNotes() {
            document.getElementById('notes-backdrop').style.display = 'none';
            document.getElementById('notes-modal').style.display = 'none';
        }
    </script>
    """

    live_tracking_js = f"""
    <script>
        var vanMarkers = {{}};
        function updateVans() {{
            fetch("{FIREBASE_URL}")
                .then(response => response.json())
                .then(data => {{
                    if(!data) return;
                    for (const [mechanic, coords] of Object.entries(data)) {{
                        if (vanMarkers[mechanic]) {{
                            vanMarkers[mechanic].setLatLng([coords.lat, coords.lng]);
                        }} else {{
                            var iconUrl = 'base_icon.png';
                            if (mechanic.toLowerCase() === 'seba') iconUrl = 'seba_icon.png';
                            if (mechanic.toLowerCase() === 'juan') iconUrl = 'juan_icon.png';
                            var vanIcon = L.icon({{ iconUrl: iconUrl, iconSize: [28, 28], iconAnchor: [14, 14] }});
                            vanMarkers[mechanic] = L.marker([coords.lat, coords.lng], {{icon: vanIcon, zIndexOffset: 10000}}).addTo({map_var_name});
                        }}
                    }}
                }})
                .catch(err => console.error("Live Tracking Error: ", err));
        }}
        
        function updateTimeLine() {{
            const now = new Date();
            const minsFrom930 = (now.getHours() * 60 + now.getMinutes()) - (9 * 60 + 30);
            const px = minsFrom930 * 1.5;
            document.querySelectorAll('.current-time-line').forEach(line => {{
                if (px >= 0 && px <= 810) {{ line.style.display = 'block'; line.style.top = px + 'px'; }} 
                else {{ line.style.display = 'none'; }}
            }});
        }}

        window.addEventListener('load', function() {{
            setInterval(updateVans, 5000); updateVans();
            setInterval(updateTimeLine, 300000); updateTimeLine();
            
            // Check if Optimizer sent a draft address via URL
            const urlParams = new URLSearchParams(window.location.search);
            if(urlParams.has('draft_address')) {{
                document.getElementById('global-draft-input').value = urlParams.get('draft_address');
                plantGlobalPin();
            }}
        }});
    </script>
    """

    drafting_html = f"""
    <div style="position:absolute; bottom:10px; left:10px; z-index:9999; background:white; padding:5px; border-radius:20px; box-shadow:0 2px 10px rgba(0,0,0,0.2); font-family:'Gotham', sans-serif; font-size:12px; display:flex; gap:5px; align-items:center; border: 2px solid {CHUM_BLUE};">
        <input type="text" id="global-draft-input" placeholder="Intercalar dirección" style="width:160px; padding:5px 10px; border:none; outline:none; font-family:'Gotham';">
        <button onclick="plantGlobalPin()" style="padding:6px 12px; background:{CHUM_BLUE}; color:white; border:none; border-radius:15px; cursor:pointer; font-weight:bold;">Marcar</button>
    </div>

    <div id="draft-modal" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); background:white; padding:20px; border-radius:8px; box-shadow:0px 4px 15px rgba(0,0,0,0.4); z-index:100005; font-family:'Gotham', sans-serif; border: 2px solid {CHUM_BLUE};">
        <h3 style="margin-top:0; font-family:'Saturn-Bold'; color:{CHUM_BLUE};">Resultados Intercalar</h3>
        <input type="text" id="modal-draft-input" style="width:250px; padding:8px; border:1px solid #ccc; border-radius:4px; margin-bottom:15px; font-family:'Gotham';">
        <div style="display:flex; justify-content:flex-end; gap:10px;">
            <button onclick="document.getElementById('draft-modal').style.display='none'" style="padding:8px 15px; border:none; border-radius:4px; cursor:pointer; background:#eee; color:#333; font-weight:bold;">Cancelar</button>
            <button onclick="calcDraft()" style="padding:8px 15px; background:{CHUM_BLUE}; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">Calcular</button>
        </div>
    </div>

    <div id="draft-info-box" style="display:none; position:absolute; bottom:60px; left:10px; z-index:9999; background:white; padding:15px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.3); font-family:'Gotham', sans-serif; font-size:13px; max-width:350px; border: 2px solid {CHUM_BLUE};">
        <div id="draft-info-header" style="font-family:'Saturn-Bold'; color:{CHUM_BLUE}; font-size:14px; margin-bottom:10px; border-bottom:1px solid #ddd; padding-bottom:5px; cursor:move; display:flex; justify-content:space-between; align-items:center;">
            <span>Resultados Intercalar</span>
        </div>
        <div id="draft-info-1" style="margin-bottom:8px; color:#444;"></div>
        <div id="draft-info-2" style="margin-bottom:15px; color:#444;"></div>
        <div style="font-weight:bold; color:{CHUM_BLUE}; font-size:15px; border-top:1px solid #eee; padding-top:10px;">Tiempo Disponible: <span id="draft-info-time"></span> min</div>
        <button onclick="closeDraftInfo()" style="margin-top:15px; width:100%; padding:8px; background:#eee; color:{CHUM_BLUE}; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">OK</button>
    </div>

    <script>
        let draftAddress = "";
        let globalPinMarker = null;
        let draftMarkers = [];
        let draftLines = [];
        let currentDraftApp = null;

        function getMapInstance() {{ return {map_var_name}; }}

        function plantGlobalPin() {{
            const inputVal = document.getElementById('global-draft-input').value;
            if (!inputVal) return;
            draftAddress = inputVal;
            document.getElementById('modal-draft-input').value = draftAddress; // Sync
            localStorage.setItem('chum_draft_address', draftAddress); // Share with Optimizer

            const geocoder = new google.maps.Geocoder();
            geocoder.geocode({{ address: draftAddress }}, function(results, status) {{
                if (status === 'OK') {{
                    if (globalPinMarker) getMapInstance().removeLayer(globalPinMarker);
                    const lat = results[0].geometry.location.lat();
                    const lng = results[0].geometry.location.lng();
                    
                    globalPinMarker = L.marker([lat, lng], {{
                        icon: L.divIcon({{html: '<div style="font-size:48px; text-align:center; line-height:48px;">📍</div>', className: 'global-pin', iconSize: [48,48], iconAnchor: [24,48]}})
                    }}).addTo(getMapInstance());

                    globalPinMarker.on('click', function() {{
                        getMapInstance().removeLayer(globalPinMarker);
                        globalPinMarker = null;
                    }});
                    getMapInstance().setView([lat, lng], 13);
                }} else {{ alert('Dirección no encontrada: ' + status); }}
            }});
        }}

        function openDraftModal(encodedData) {{
            currentDraftApp = JSON.parse(decodeURIComponent(encodedData));
            const savedDraft = localStorage.getItem('chum_draft_address') || draftAddress;
            document.getElementById('modal-draft-input').value = savedDraft;
            document.getElementById('draft-modal').style.display = 'block';
        }}

        function closeDraftInfo() {{
            document.getElementById('draft-info-box').style.display = 'none';
            draftLines.forEach(l => getMapInstance().removeLayer(l));
            draftMarkers.forEach(m => getMapInstance().removeLayer(m));
            draftLines = []; draftMarkers = [];
        }}

        function calcDraft() {{
            const inputVal = document.getElementById('modal-draft-input').value;
            if (!inputVal) return;
            draftAddress = inputVal;
            document.getElementById('global-draft-input').value = draftAddress; // Sync
            localStorage.setItem('chum_draft_address', draftAddress);
            document.getElementById('draft-modal').style.display = 'none';
            closeDraftInfo();

            const appData = currentDraftApp;
            const dirService = new google.maps.DirectionsService();

            dirService.route({{
                origin: new google.maps.LatLng(appData.lat, appData.lng), destination: draftAddress, travelMode: 'DRIVING'
            }}, function(res1, status1) {{
                if (status1 !== 'OK') {{ alert('No se pudo rutear al draft: ' + status1); return; }}

                dirService.route({{
                    origin: draftAddress, destination: new google.maps.LatLng(appData.next_lat, appData.next_lng), travelMode: 'DRIVING'
                }}, function(res2, status2) {{
                    if (status2 !== 'OK') {{ alert('No se pudo rutear al siguiente destino: ' + status2); return; }}

                    const pts1 = res1.routes[0].overview_path.map(p => [p.lat(), p.lng()]);
                    const pts2 = res2.routes[0].overview_path.map(p => [p.lat(), p.lng()]);
                    draftLines.push(L.polyline(pts1, {{color: '{CHUM_BLUE}', dashArray: '5, 10', weight: 4}}).addTo(getMapInstance()));
                    draftLines.push(L.polyline(pts2, {{color: '{CHUM_BLUE}', dashArray: '5, 10', weight: 4}}).addTo(getMapInstance()));

                    const draftLoc = res1.routes[0].legs[0].end_location;
                    draftMarkers.push(L.marker([draftLoc.lat(), draftLoc.lng()], {{
                        icon: L.divIcon({{html: '<div style="font-size:24px;">🚧</div>', className: 'draft-icon', iconSize:[24,24], iconAnchor:[12,12]}})
                    }}).addTo(getMapInstance()));

                    const sec1 = res1.routes[0].legs[0].duration_in_traffic ? res1.routes[0].legs[0].duration_in_traffic.value : res1.routes[0].legs[0].duration.value;
                    const sec2 = res2.routes[0].legs[0].duration_in_traffic ? res2.routes[0].legs[0].duration_in_traffic.value : res2.routes[0].legs[0].duration.value;

                    const min1 = Math.round((sec1 * 1.07) / 60);
                    const min2 = Math.round((sec2 * 1.07) / 60);

                    let availMins = Math.round((appData.next_start_ts - appData.end_time_ts) / 60) - (min1 + min2);
                    if (availMins < 0) availMins = 0;

                    document.getElementById('draft-info-1').innerHTML = `<b style="color:{CHUM_BLUE};">${{min1}} min</b> ${{appData.address}} hasta <b>${{draftAddress}}</b>`;
                    document.getElementById('draft-info-2').innerHTML = `<b style="color:{CHUM_BLUE};">${{min2}} min</b> <b>${{draftAddress}}</b> hasta ${{appData.next_address}}`;
                    document.getElementById('draft-info-time').innerText = availMins;
                    document.getElementById('draft-info-box').style.display = 'block';
                }});
            }});
        }}

        // Make the draft info box draggable
        dragElement(document.getElementById("draft-info-box"));
        function dragElement(elmnt) {{
            var pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
            if (document.getElementById("draft-info-header")) {{
                document.getElementById("draft-info-header").onmousedown = dragMouseDown;
            }} else {{
                elmnt.onmousedown = dragMouseDown;
            }}
            function dragMouseDown(e) {{
                e = e || window.event;
                e.preventDefault();
                pos3 = e.clientX;
                pos4 = e.clientY;
                document.onmouseup = closeDragElement;
                document.onmousemove = elementDrag;
            }}
            function elementDrag(e) {{
                e = e || window.event;
                e.preventDefault();
                pos1 = pos3 - e.clientX;
                pos2 = pos4 - e.clientY;
                pos3 = e.clientX;
                pos4 = e.clientY;
                elmnt.style.bottom = "auto";
                elmnt.style.top = (elmnt.offsetTop - pos2) + "px";
                elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
            }}
            function closeDragElement() {{
                document.onmouseup = null;
                document.onmousemove = null;
            }}
        }}
    </script>
    """
    
    desktop_layout = f"""
    {BRAND_CSS}
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; overflow: hidden; background: #f4f6f8; font-family: 'Gotham', sans-serif; }}
        .leaflet-container {{ width: 63vw !important; height: 100vh !important; position: absolute !important; left: 0 !important; top: 0 !important; }}
        .leaflet-control-layers-list::before {{ content: 'Ruta'; display: block; font-weight: bold; margin-bottom: 5px; border-bottom: 1px solid #ccc; padding-bottom: 3px; font-family: 'Saturn-Bold', sans-serif; color: {CHUM_BLUE};}}
        .leaflet-control-layers-base {{ display: none; }}
        .leaflet-control-layers {{ border: 2px solid {CHUM_BLUE} !important; border-radius: 8px !important; color: {CHUM_BLUE} !important; font-family: 'Gotham', sans-serif; }}
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-track {{ background: #f1f1f1; }}
        ::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: {CHUM_BLUE}; }}
        {anim_css}
    </style>
    
    <div id="desktop-side-panel" style="width: 37vw; height: 100vh; position: absolute; right: 0; top: 0; background: white; z-index: 9999; box-shadow: -4px 0 15px rgba(0,0,0,0.05); display: flex; flex-direction: column;">
        <div style="padding: 12px 15px; background: {CHUM_BLUE}; color: white; font-family: 'Saturn-Bold', sans-serif; font-size: 16px; font-weight: normal; flex-shrink: 0; text-align: center; text-transform: uppercase;">
            Planificación Diaria: {display_date}
        </div>
        <div style="display: flex; flex-direction: row; flex-grow: 1; overflow: hidden; width: 100%;">
            {mechanics_container_html}
        </div>
    </div>
    {carousel_html}
    {modal_html}
    {drafting_html}
    {live_tracking_js}
    """
    
    m.get_root().html.add_child(folium.Element(desktop_layout))
    m.save(f"desktop_map_{date_str}.html")

def generate_optimizer_page(base_date):
    # This generates a completely standalone Optimizer HTML tool that acts as a wrapper 
    # to control the desktop maps via an iframe!
    html_content = f"""<!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Optimización de Agendamiento</title>
        <script src="https://maps.googleapis.com/maps/api/js?key={GMAPS_KEY}"></script>
        <link rel="icon" type="image/png" sizes="32x32" href="favicon-32x32.png">
        <style>
            {BRAND_CSS}
            body, html {{ margin: 0; padding: 0; height: 100%; overflow: hidden; background: #f4f6f8; }}
            .panel {{ width: 37vw; height: 100vh; position: absolute; right: 0; top: 0; background: white; z-index: 9999; box-shadow: -4px 0 15px rgba(0,0,0,0.05); display: flex; flex-direction: column; }}
            .header {{ padding: 12px 15px; background: {CHUM_BLUE}; color: white; font-family: 'Saturn-Bold', sans-serif; font-size: 16px; text-align: center; text-transform: uppercase; }}
            .inputs-container {{ padding: 20px; background: #f8f9fa; border-bottom: 1px solid #ddd; }}
            .input-row {{ display: flex; gap: 10px; margin-bottom: 15px; align-items: center; justify-content: space-between; }}
            input {{ padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; font-family: 'Gotham'; outline: none; }}
            .address-input {{ flex-grow: 1; width: 100%; }}
            .num-input {{ width: 60px; text-align: center; }}
            .btn-optimizar {{ width: 100%; padding: 12px; background: {CHUM_BLUE}; color: white; border: none; border-radius: 4px; font-family: 'Saturn-Bold'; font-size: 14px; cursor: pointer; text-transform: uppercase; }}
            .btn-optimizar:hover {{ background: #022b5e; }}
            .results-container {{ flex-grow: 1; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 15px; background: #fff; }}
            
            .pill {{ display: flex; border: 1px solid #ddd; border-radius: 12px; overflow: hidden; cursor: pointer; box-shadow: 0 3px 8px rgba(0,0,0,0.08); transition: transform 0.1s; background: white; }}
            .pill:hover {{ transform: translateY(-2px); box-shadow: 0 5px 12px rgba(0,0,0,0.15); border-color: {CHUM_BLUE}; }}
            .pill-endcap {{ width: 40px; display: flex; flex-direction: column; justify-content: center; align-items: center; color: white; font-weight: bold; font-size: 11px; flex-shrink: 0; padding: 5px; text-align: center; }}
            .pill-body {{ flex-grow: 1; display: flex; align-items: center; font-size: 10px; color: #444; padding: 5px; }}
            .transit-box {{ background: #222; color: white; padding: 3px 6px; border-radius: 4px; font-weight: bold; margin: 0 5px; white-space: nowrap; }}
            .address-text {{ flex: 1; text-align: center; padding: 0 5px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
            
            .loading {{ text-align: center; padding: 30px; font-family: 'Saturn-Bold'; color: {CHUM_BLUE}; font-size: 18px; }}
        </style>
    </head>
    <body>
        <iframe id="map-frame" src="desktop_map_{base_date.strftime('%Y-%m-%d')}.html" style="width: 63vw; height: 100vh; border: none; position: absolute; left: 0; top: 0;"></iframe>
        
        <div class="panel">
            <div class="header">Optimización de Agendamiento</div>
            
            <div class="inputs-container">
                <div class="input-row">
                    <input type="text" id="opt-address" class="address-input" placeholder="Nueva Dirección">
                </div>
                <div class="input-row" style="justify-content: flex-start; gap: 20px;">
                    <label style="font-weight:bold; color:{CHUM_BLUE}; font-size:12px;">Duración <input type="number" id="opt-dur" class="num-input" value="60"></label>
                    <label style="font-weight:bold; color:{CHUM_BLUE}; font-size:12px;">Holgura <input type="number" id="opt-cush" class="num-input" value="30"></label>
                </div>
                <button class="btn-optimizar" onclick="runOptimization()">Optimizar</button>
            </div>
            
            <div id="results" class="results-container">
                <div style="text-align:center; color:#8A9892; margin-top:20px; font-size:12px;">Ingresa una dirección y presiona Optimizar para buscar los mejores horarios en los próximos 3 días.</div>
            </div>
        </div>

        <script>
            let allAppointments = [];
            const mechanicColors = {{ 'Juan': '#dc3545', 'Seba': '#007bff', 'Base': '#8A9892' }};
            const baseLocation = "-33.45219480797122, -70.5787333882418";
            
            // Generate the 3 target dates
            const today = new Date('{base_date.isoformat()}');
            const targetDates = [
                today.toISOString().split('T')[0],
                new Date(today.getTime() + 86400000).toISOString().split('T')[0],
                new Date(today.getTime() + 172800000).toISOString().split('T')[0]
            ];

            // On Load
            window.onload = function() {{
                const savedAddress = localStorage.getItem('chum_draft_address');
                if(savedAddress) document.getElementById('opt-address').value = savedAddress;
                
                fetch('{CACHE_FILE}')
                    .then(r => r.json())
                    .then(data => {{
                        allAppointments = Object.values(data);
                    }});
            }};

            function runOptimization() {{
                const newAddress = document.getElementById('opt-address').value;
                const dur = parseInt(document.getElementById('opt-dur').value);
                const cush = parseInt(document.getElementById('opt-cush').value);
                const resultsDiv = document.getElementById('results');
                
                if(!newAddress) return alert("Ingresa una dirección primero.");
                localStorage.setItem('chum_draft_address', newAddress);
                
                resultsDiv.innerHTML = '<div class="loading">Calculando Rutas...</div>';

                let validGaps = [];

                // 1. Build Schedules and Find Gaps
                targetDates.forEach(dateStr => {{
                    ['Juan', 'Seba'].forEach(mech => {{
                        // Get apps for this day/mech, sorted
                        let dayApps = allAppointments.filter(a => a.start_dt.startsWith(dateStr) && a.mechanic === mech);
                        dayApps.sort((a, b) => a.start_timestamp - b.start_timestamp);
                        
                        let schedule = [];
                        // Base Start
                        let dObj = new Date(dateStr + "T09:30:00-04:00");
                        schedule.push({{ id: 'Base', address: baseLocation, ts: dObj.getTime()/1000, isBase: true }});
                        
                        dayApps.forEach((a, idx) => {{
                            schedule.push({{ id: mech[0] + (idx+1), address: a.route_address, ts: a.start_timestamp, dur: a.duration, isBase: false }});
                        }});
                        
                        // Base End (17:30 constraint)
                        let endObj = new Date(dateStr + "T17:30:00-04:00");
                        schedule.push({{ id: 'Base', address: baseLocation, ts: endObj.getTime()/1000, isBase: true }});
                        
                        // Find gaps
                        for(let i=0; i < schedule.length - 1; i++) {{
                            let prev = schedule[i];
                            let next = schedule[i+1];
                            
                            let prevEndTime = prev.isBase ? prev.ts : (prev.ts + (prev.dur * 60));
                            let availableMins = (next.ts - prevEndTime) / 60;
                            
                            if (availableMins >= (dur + cush)) {{
                                validGaps.push({{
                                    date: dateStr, mechanic: mech,
                                    prev: prev, next: next,
                                    availableMins: availableMins
                                }});
                            }}
                        }}
                    }});
                }});

                if(validGaps.length === 0) {{
                    resultsDiv.innerHTML = '<div style="text-align:center; color:red; padding:20px;">No hay bloques de tiempo suficientemente grandes.</div>';
                    return;
                }}

                // 2. Call Google Distance Matrix
                const matrix = new google.maps.DistanceMatrixService();
                
                // We need travel times: Prev -> New, and New -> Next
                let originsLeg1 = validGaps.map(g => g.prev.address);
                let destsLeg2 = validGaps.map(g => g.next.address);
                
                // We batch this in 2 calls. (Assuming < 25 gaps. If more, we slice it, but usually fine for 3 days).
                let originsSliced = originsLeg1.slice(0, 25);
                let destsSliced = destsLeg2.slice(0, 25);
                let processingGaps = validGaps.slice(0, 25); // cap at 25 for API limits
                
                matrix.getDistanceMatrix({{
                    origins: originsSliced, destinations: [newAddress], travelMode: 'DRIVING'
                }}, function(res1, status1) {{
                    if(status1 !== 'OK') return resultsDiv.innerHTML = 'Error API Leg 1';
                    
                    matrix.getDistanceMatrix({{
                        origins: [newAddress], destinations: destsSliced, travelMode: 'DRIVING'
                    }}, function(res2, status2) {{
                        if(status2 !== 'OK') return resultsDiv.innerHTML = 'Error API Leg 2';
                        
                        let finalOptions = [];
                        
                        for(let i=0; i < processingGaps.length; i++) {{
                            let gap = processingGaps[i];
                            let elem1 = res1.rows[i].elements[0];
                            let elem2 = res2.rows[0].elements[i];
                            
                            if(elem1.status === 'OK' && elem2.status === 'OK') {{
                                let min1 = Math.round((elem1.duration.value * 1.07) / 60);
                                let min2 = Math.round((elem2.duration.value * 1.07) / 60);
                                let totalDrive = min1 + min2;
                                
                                // Final check: does it actually fit with driving time?
                                if (gap.availableMins >= (dur + min1 + min2)) {{
                                    gap.min1 = min1;
                                    gap.min2 = min2;
                                    gap.totalDrive = totalDrive;
                                    finalOptions.push(gap);
                                }}
                            }}
                        }}
                        
                        // Sort by lowest driving time
                        finalOptions.sort((a, b) => a.totalDrive - b.totalDrive);
                        renderResults(finalOptions, newAddress);
                    }});
                }});
            }}
            
            function renderResults(options, newAddress) {{
                const resultsDiv = document.getElementById('results');
                if(options.length === 0) {{
                    resultsDiv.innerHTML = '<div style="text-align:center; padding:20px;">Ningun bloque cumple con el tiempo de viaje necesario.</div>';
                    return;
                }}
                
                let html = '';
                options.forEach(opt => {{
                    let dateObj = new Date(opt.date + "T12:00:00");
                    let dateDisplay = dateObj.toLocaleDateString('es-ES', {{ weekday: 'short', day: 'numeric', month:'short' }});
                    let mechColor = mechanicColors[opt.mechanic];
                    let pTime = new Date(opt.prev.isBase ? opt.prev.ts*1000 : (opt.prev.ts + opt.prev.dur*60)*1000).toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit'}});
                    let nTime = new Date(opt.next.ts*1000).toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit'}});
                    
                    // The magic click: Load map for that day, and set parameters to auto-draft
                    let onClick = `loadMapForDraft('${{opt.date}}', '${{opt.mechanic}}')`;
                    
                    html += `
                    <div class="pill" onclick="${{onClick}}">
                        <div class="pill-endcap" style="background:${{mechColor}};">
                            <span style="font-size:14px; margin-bottom:2px;">${{opt.prev.id}}</span>
                            <span>${{pTime}}</span>
                        </div>
                        
                        <div class="pill-body">
                            <div class="address-text">${{opt.prev.address.split(',')[0]}}</div>
                            <div class="transit-box">${{opt.min1}}</div>
                            <div class="address-text" style="color:{CHUM_BLUE}; font-weight:bold;">
                                ${{dateDisplay}}<br>${{newAddress.split(',')[0]}}
                            </div>
                            <div class="transit-box">${{opt.min2}}</div>
                            <div class="address-text">${{opt.next.address.split(',')[0]}}</div>
                        </div>
                        
                        <div class="pill-endcap" style="background:${{opt.next.id === 'Base' ? '#8A9892' : mechColor}};">
                            <span style="font-size:14px; margin-bottom:2px;">${{opt.next.id}}</span>
                            <span>${{nTime}}</span>
                        </div>
                    </div>`;
                }});
                resultsDiv.innerHTML = html;
            }}

            function loadMapForDraft(dateStr, mechanic) {{
                const iframe = document.getElementById('map-frame');
                iframe.src = `desktop_map_${{dateStr}}.html?draft_address=${{encodeURIComponent(document.getElementById('opt-address').value)}}&mechanic=${{mechanic}}`;
            }}
        </script>
    </body>
    </html>"""
    
    with open("optimizer.html", "w", encoding='utf-8') as f:
        f.write(html_content)

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
        except Exception as e: pass
                
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
        
    # Generate the new Optimizer tool
    generate_optimizer_page(base_date)
    
    update_distance_csv()
    
    with open("desktop_map.html", "w") as f:
        f.write(f'''
        <!DOCTYPE html>
        <html>
        <head><meta http-equiv="refresh" content="0; url=desktop_map_{base_date.strftime('%Y-%m-%d')}.html" /></head>
        <body style="font-family: 'Gotham', sans-serif; text-align: center; padding-top: 20%; color: {CHUM_BLUE};">
            <h2>Cargando Centro de Control...</h2>
        </body>
        </html>
        ''')