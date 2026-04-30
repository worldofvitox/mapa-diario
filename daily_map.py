import os
import re
import requests
import googlemaps
import folium
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar
import json
import urllib.parse
import csv
import unicodedata

GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')

BASE_LOCATION = [-33.45219480797122, -70.5787333882418] 
CALENDAR_URL = 'https://calendar.google.com/calendar/ical/c_0e3e9c70ab1527edfef805c43e9fd06dabb0fdfab8e5081f4feb40565337708b%40group.calendar.google.com/private-a534c46e66604fef2e96a3dc4810f688/basic.ics'
CACHE_FILE = 'appointments_cache.json'
CONFIG_URL = 'https://docs.google.com/spreadsheets/d/1Sgtl_4Fm88-vVMfCrGxULl1Tg0ekD6rXT-P59hUlVSw/export?format=csv'

CHUM_BLUE = "#011E41"

MECHANICS = {
    'Juan': {'palette': ['#dc3545', '#c82333', '#a71d2a', '#e4606d', '#eb8c95'], 'initial': 'J', 'offset': (0.00012, 0.00012)},
    'Seba': {'palette': ['#007bff', '#0056b3', '#004085', '#3399ff', '#66b2ff'], 'initial': 'S', 'offset': (-0.00012, -0.00012)}
}

BRAND_CSS = """
@font-face { font-family: 'Saturn-Bold'; src: url('Saturn-Bold.woff') format('woff'), url('Saturn-Bold.ttf') format('truetype'); }
@font-face { font-family: 'Gotham'; src: url('Gotham Book.otf') format('opentype'); font-weight: normal; }
@font-face { font-family: 'Gotham'; src: url('Gotham Bold.otf') format('opentype'); font-weight: bold; }
@font-face { font-family: 'Gotham'; src: url('Gotham Medium.otf') format('opentype'); font-weight: 500; }
body, html { font-family: 'Gotham', sans-serif; }
::placeholder { font-family: 'Gotham', sans-serif !important; opacity: 0.6; }
"""

CARD_STYLE = (
    "font-family: 'Gotham', sans-serif; font-size: 11px; font-weight: bold; "
    "background-color: white; padding: 5px 10px; border-radius: 8px; "
    "box-shadow: 0px 3px 8px rgba(0,0,0,0.15); white-space: nowrap; "
    "display: inline-flex; align-items: center; border: none;"
)

WAZE_ICON_URL = "waze.png" 

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
                    'abbrev': abbrev, 'prod': prod, 'var': var, 'comb': comb, 'shorthand': shorthand, 'duration': duration
                })
    except: pass
    return config

GLOBAL_CONFIG = get_service_config()

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

def get_appointments():
    live_apps = []
    now_dt = datetime.now(timezone)
    if now_dt.hour >= 18: target_date = (now_dt + timedelta(days=1)).date()
    else: target_date = now_dt.date()
    
    try:
        response = requests.get(CALENDAR_URL, timeout=15)
        if response.status_code == 200:
            gcal = Calendar.from_ical(response.content)
            for component in gcal.walk():
                if component.name == "VEVENT":
                    start_dt = component.get('dtstart').dt
                    if not isinstance(start_dt, datetime):
                        start_dt = timezone.localize(datetime.combine(start_dt, datetime.min.time())).replace(hour=9)
                    else: start_dt = start_dt.astimezone(timezone)

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
                    
                    raw_phone = extract_var(clean_desc, "Telefono") or extract_var(clean_desc, "Teléfono")
                    clean_phone = re.sub(r'\D', '', raw_phone)
                    if len(clean_phone) == 9: clean_phone = "56" + clean_phone
                    
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
                        'abbrev': abbrev, 'duration': duration, 'shorthand': shorthand, 'phone': clean_phone, 'notas': raw_notas
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
        if app['start_dt'].date() == target_date: final_apps.append(app)

    return final_apps

def generate_map():
    appointments = get_appointments()
    m = folium.Map(location=BASE_LOCATION, zoom_start=13, tiles=None)
    
    favicon_html = f"""
    {BRAND_CSS}
    <link rel="icon" type="image/x-icon" href="favicon.ico?v=2">
    <link rel="icon" type="image/png" sizes="32x32" href="favicon-32x32.png?v=2">
    <link rel="icon" type="image/png" sizes="16x16" href="favicon-16x16.png?v=2">
    <link rel="apple-touch-icon" href="apple-touch-icon.png?v=2">
    """
    m.get_root().header.add_child(folium.Element(favicon_html))
    
    folium.TileLayer('cartodbpositron', control=False).add_to(m)
    folium.Marker(location=BASE_LOCATION, icon=folium.CustomIcon('base_icon.png', icon_size=(28, 28))).add_to(m)
    
    all_points_for_zoom = [BASE_LOCATION]
    table_rows_html = ""

    ordered_mechs = ['Juan', 'Seba']
    now_dt = datetime.now(timezone)
    
    for name in ordered_mechs:
        info = MECHANICS[name]
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = sorted([a for a in appointments if a['mechanic'] == name], key=lambda x: x['start_dt'])
        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        for i, app in enumerate(mech_apps):
            label_id = f"{info['initial']}{i+1}"
            leg_color = info['palette'][i % len(info['palette'])]
            arrival_target = app['start_dt']
            
            if arrival_target.date() > now_dt.date(): directions = gmaps.directions(current_loc, app['route_address'], mode="driving")
            elif arrival_target > now_dt: directions = gmaps.directions(current_loc, app['route_address'], mode="driving", arrival_time=arrival_target)
            else: directions = gmaps.directions(current_loc, app['route_address'], mode="driving", departure_time=now_dt)

            if directions:
                leg = directions[0]['legs'][0]
                raw_seconds = leg.get('duration_in_traffic', leg['duration'])['value']
                penalty_seconds = 180 if app['address2'] else 0
                buffered_seconds = (raw_seconds * 1.07) + penalty_seconds
                buffered_mins = round(buffered_seconds / 60)
                departure_dt = arrival_target - timedelta(seconds=buffered_seconds)
                
                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                all_points_for_zoom.extend(raw_pts)
                points = apply_offset(raw_pts, info['offset'])
                folium.PolyLine(points, color=leg_color, weight=6, opacity=0.85).add_to(fg)

                mid = points[len(points)//2]
                encoded_address = urllib.parse.quote(app['route_address']).replace("'", "%27")
                waze_link = f"https://waze.com/ul?q={encoded_address}&navigate=yes"
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:{leg_color}; transform:translateY(-20px); font-family:'Gotham', sans-serif;"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{label_id} / {departure_dt.strftime('%H:%M')} / {buffered_mins} min</div></a>''')).add_to(fg)

                short_cust_name = app['name'][:20]
                display_addr1 = app['address1'][:20] + "..." if len(app['address1']) > 20 else app['address1']
                end_pt = apply_offset([(leg['end_location']['lat'], leg['end_location']['lng'])], info['offset'])[0]
                pill_content = f'<span style="font-family:\'Gotham\'; font-weight:bold;">{label_id} / {app["start_dt"].strftime("%H:%M")} / {short_cust_name}</span> / <span style="font-family:\'Gotham\'; font-weight:normal;">{display_addr1}</span>'
                
                if app.get('phone'):
                    cust_first_name = app['name'].split()[0].replace("'", "\\'")
                    mech_name = app['mechanic'].replace("'", "\\'")
                    orig_time = app['start_dt'].strftime('%H:%M')
                    phone = app['phone']
                    pill_html = f'<div onclick="openWaModal(\'{phone}\', \'{cust_first_name}\', \'{mech_name}\', \'{orig_time}\')" style="{CARD_STYLE} color:{CHUM_BLUE}; transform:translate(-10%, -50%); pointer-events:auto; cursor:pointer; box-shadow: 0px 4px 10px rgba(0,0,0,0.3); border: 1px solid #ddd;">{pill_content}</div>'
                else:
                    pill_html = f'<div style="{CARD_STYLE} color:{CHUM_BLUE}; transform:translate(-10%, -50%); pointer-events:none;">{pill_content}</div>'
                
                folium.Marker(location=end_pt, icon=folium.DivIcon(html=pill_html)).add_to(fg)
                
                table_address = f"{app['address1']} {app['address2']} {app['comuna']}".strip()
                encoded_notas = urllib.parse.quote(app.get('notas', '')).replace("'", "%27")
                
                table_rows_html += f"""
                <tr style="border-bottom: 1px solid #eee; cursor: pointer;" onclick="showNotes(decodeURIComponent('{encoded_notas}'))">
                    <td style="padding: 4px 2px; color: {leg_color}; width: 6%; white-space: nowrap; vertical-align: middle;">{label_id}</td>
                    <td style="padding: 4px 2px; width: 10%; white-space: nowrap; vertical-align: middle;">{app['start_dt'].strftime('%H:%M')}</td>
                    <td style="padding: 4px 2px; width: 23%; font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 0; vertical-align: middle;">{short_cust_name}</td>
                    <td style="padding: 4px 2px; width: 51%; font-size: 10px; color: #666; white-space: normal; line-height: 1.1; vertical-align: middle;">{table_address}</td>
                    <td style="padding: 4px 2px; font-size: 10px; color: #444; width: 10%; white-space: nowrap; text-align: right; vertical-align: middle;">{app['abbrev']}</td>
                </tr>
                """
                current_loc = app['route_address']

        if mech_apps:
            base_str = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
            return_target = mech_apps[-1]['start_dt'] + timedelta(hours=1)
            
            if return_target.date() > now_dt.date(): directions = gmaps.directions(current_loc, base_str, mode="driving")
            elif return_target > now_dt: directions = gmaps.directions(current_loc, base_str, mode="driving", departure_time=return_target)
            else: directions = gmaps.directions(current_loc, base_str, mode="driving", departure_time=now_dt)

            if directions:
                leg = directions[0]['legs'][0]
                raw_seconds = leg.get('duration_in_traffic', leg['duration'])['value']
                buffered_mins = round((raw_seconds * 1.07) / 60)
                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                all_points_for_zoom.extend(raw_pts)
                points = apply_offset(raw_pts, info['offset'])
                folium.PolyLine(points, color=info['palette'][0], weight=5, opacity=0.6, dash_array='7, 7').add_to(fg)
                mid = points[len(points)//2]
                waze_link = f"https://waze.com/ul?ll={BASE_LOCATION[0]},{BASE_LOCATION[1]}&navigate=yes"
                base_label = f"{info['initial']}{len(mech_apps) + 1}"
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:#8A9892; transform:translateY(-20px); font-family:'Gotham', sans-serif;"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{base_label} / Base / {buffered_mins} min</div></a>''')).add_to(fg)

    folium.LayerControl(collapsed=False).add_to(m)

    if len(all_points_for_zoom) > 1:
        lats, lngs = zip(*all_points_for_zoom)
        sw, ne = [min(lats), min(lngs)], [max(lats), max(lngs)]
        height = ne[0] - sw[0]
        m.fit_bounds([[sw[0] - (height * 0.45), sw[1]], ne])

    if not table_rows_html: table_rows_html = f'<tr><td colspan="5" style="text-align:left; padding: 10px; font-weight:normal; font-size:10px;"><b>No hay rutas para este dia.</b></td></tr>'

    modal_html = f"""
    <div id="notes-backdrop" onclick="closeNotes()" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(1,30,65,0.4); z-index:100000;"></div>
    <div id="notes-modal" onclick="event.stopPropagation()" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); background:white; padding:20px; border-radius:8px; box-shadow:0px 4px 15px rgba(0,0,0,0.3); z-index:100001; min-width:300px; max-width:80%; max-height:80vh; overflow-y:auto; font-family:'Gotham', sans-serif; font-size:14px; font-weight:normal; color:{CHUM_BLUE}; border: 2px solid {CHUM_BLUE};">
        <div style="margin-bottom: 10px; font-size: 11px; color: #8A9892; text-transform: uppercase; font-family:'Saturn-Bold';">Notas de la Cita</div>
        <div id="notes-content" style="user-select:text; white-space: pre-wrap; line-height: 1.4;"></div>
        <div style="margin-top: 15px; text-align: right;"><button onclick="closeNotes()" style="background:{CHUM_BLUE}; color:white; border:none; padding:5px 15px; border-radius:4px; cursor:pointer; font-family:'Gotham'; font-weight:bold;">Cerrar</button></div>
    </div>
    <script>
        function showNotes(text) {{
            document.getElementById('notes-content').textContent = (!text || text.trim() === '') ? 'Sin notas para esta cita.' : text;
            document.getElementById('notes-backdrop').style.display = 'block';
            document.getElementById('notes-modal').style.display = 'block';
        }}
        function closeNotes() {{
            document.getElementById('notes-backdrop').style.display = 'none';
            document.getElementById('notes-modal').style.display = 'none';
        }}
    </script>
    """

    wa_modal_html = f"""
    <div id="wa-backdrop" onclick="closeWaModal()" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(1,30,65,0.5); z-index:100004;"></div>
    <div id="wa-modal" onclick="event.stopPropagation()" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); background:white; padding:20px; border-radius:12px; box-shadow:0px 4px 15px rgba(0,0,0,0.4); z-index:100005; width:85%; max-width:380px; font-family:'Gotham', sans-serif; max-height:90vh; overflow-y:auto; border: 2px solid {CHUM_BLUE};">
        <div style="margin-bottom: 15px; font-size: 14px; color: {CHUM_BLUE}; font-family:'Saturn-Bold'; text-align:center;">Contactar a <span id="wa-cust-name"></span></div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <button onclick="sendWa('hablar')" style="background:#25D366; color:white; border:none; padding:15px 5px; border-radius:8px; font-family:'Gotham'; font-weight:bold; cursor:pointer; font-size:14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">Hablar</button>
            <button onclick="sendWa('voy')" style="background:#007bff; color:white; border:none; padding:15px 5px; border-radius:8px; font-family:'Gotham'; font-weight:bold; cursor:pointer; font-size:14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">Voy</button>
            
            <div style="background:#fff3cd; border:1px solid #ffeeba; border-radius:8px; padding:10px; display:flex; flex-direction:column; align-items:center; gap:8px;">
                <span style="font-size:13px; font-family:'Saturn-Bold'; color:#856404;">Tarde</span>
                <div style="display:flex; align-items:center; gap:5px;">
                    <input type="number" id="mins-tarde" placeholder="00" min="5" max="95" step="5" style="width:50px; text-align:center; padding:5px; border:1px solid #ccc; border-radius:4px; font-size:14px; box-sizing:border-box; font-family:'Gotham';">
                    <span style="font-size:12px; color:#666;">min</span>
                </div>
                <button onclick="sendWa('tarde')" style="background:#ffc107; color:#333; border:none; padding:8px; width:100%; border-radius:4px; font-family:'Gotham'; font-weight:bold; cursor:pointer;">Enviar</button>
            </div>
            
            <div style="background:#d4edda; border:1px solid #c3e6cb; border-radius:8px; padding:10px; display:flex; flex-direction:column; align-items:center; gap:8px;">
                <span style="font-size:13px; font-family:'Saturn-Bold'; color:#155724;">Temprano</span>
                <div style="display:flex; align-items:center; gap:5px;">
                    <input type="number" id="mins-temprano" placeholder="00" min="5" max="95" step="5" style="width:50px; text-align:center; padding:5px; border:1px solid #ccc; border-radius:4px; font-size:14px; box-sizing:border-box; font-family:'Gotham';">
                    <span style="font-size:12px; color:#666;">min</span>
                </div>
                <button onclick="sendWa('temprano')" style="background:#28a745; color:white; border:none; padding:8px; width:100%; border-radius:4px; font-family:'Gotham'; font-weight:bold; cursor:pointer;">Enviar</button>
            </div>

            <div style="background:#d1ecf1; border:1px solid #bee5eb; border-radius:8px; padding:10px; display:flex; flex-direction:column; gap:8px;">
               <span style="font-size:13px; font-family:'Saturn-Bold'; color:#0c5460; text-align:center;">Llegué</span>
               <div style="font-size:11px; color:#444; display:flex; flex-direction:column; gap:4px; line-height:1.2;">
                   <label><input type="radio" name="llegue_opt" value="normal" checked> Normal</label>
                   <label><input type="radio" name="llegue_opt" value="avisar"> Avisar</label>
                   <label><input type="radio" name="llegue_opt" value="porton"> Portón</label>
                   <label><input type="radio" name="llegue_opt" value="donde"> Donde</label>
               </div>
               <button onclick="sendWa('llegue')" style="background:#17a2b8; color:white; border:none; padding:8px; width:100%; border-radius:4px; font-family:'Gotham'; font-weight:bold; cursor:pointer;">Enviar</button>
           </div>

           <div style="background:#e2d9f3; border:1px solid #d3c2ee; border-radius:8px; padding:10px; display:flex; flex-direction:column; gap:8px;">
               <span style="font-size:13px; font-family:'Saturn-Bold'; color:#3b1c6e; text-align:center;">Listo</span>
               <div style="font-size:11px; color:#444; display:flex; flex-direction:column; gap:4px; line-height:1.2;">
                   <label><input type="radio" name="listo_opt" value="buscar" checked> Buscar</label>
                   <label><input type="radio" name="listo_opt" value="proxima"> Proxima</label>
                   <label><input type="radio" name="listo_opt" value="recibir"> Recibir</label>
                   <label><input type="radio" name="listo_opt" value="conserje"> Conserje</label>
               </div>
               <button onclick="sendWa('listo')" style="background:#6f42c1; color:white; border:none; padding:8px; width:100%; border-radius:4px; font-family:'Gotham'; font-weight:bold; cursor:pointer;">Enviar</button>
           </div>
        </div>
        <div style="margin-top: 15px; text-align: center;">
            <button onclick="closeWaModal()" style="background:#eee; color:{CHUM_BLUE}; border:none; padding:8px 20px; border-radius:4px; cursor:pointer; font-family:'Gotham'; font-weight:bold; font-size:12px;">Cancelar</button>
        </div>
    </div>
    <script>
        let currentWaData = {{}};
        function openWaModal(phone, custName, mechName, origTime) {{
            currentWaData = {{ phone, custName, mechName, origTime }};
            document.getElementById('wa-cust-name').innerText = custName;
            document.getElementById('mins-tarde').value = '';
            document.getElementById('mins-temprano').value = '';
            document.getElementById('wa-backdrop').style.display = 'block';
            document.getElementById('wa-modal').style.display = 'block';
        }}
        function closeWaModal() {{
            document.getElementById('wa-backdrop').style.display = 'none';
            document.getElementById('wa-modal').style.display = 'none';
        }}
        function calculateNewTime(origTime, minsOffset) {{
            let parts = origTime.split(':');
            let d = new Date(); d.setHours(parseInt(parts[0], 10)); d.setMinutes(parseInt(parts[1], 10) + minsOffset);
            return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
        }}
        function sendWa(type) {{
            let phone = currentWaData.phone; let cName = currentWaData.custName;
            let mName = currentWaData.mechName; let oTime = currentWaData.origTime;
            let text = "";
            
            if (type === 'hablar') {{ window.open('https://wa.me/' + phone, '_blank'); closeWaModal(); return; }} 
            else if (type === 'voy') {{ text = `Hola ${{cName}}! Te habla ${{mName}}, tu mecánico asignado por Chum para el día de hoy, para avisarte que ya estamos en camino hacia ti y tu bici. Cuando hayamos llegado te avisaremos por esta vía. Si hay cualquier instrucción especifica para llegar, porfa avísanos.`; }} 
            else if (type === 'temprano') {{
                let mins = parseInt(document.getElementById('mins-temprano').value, 10);
                if (isNaN(mins) || mins <= 0) {{ alert('Ingresa un número válido.'); return; }}
                text = `Hola ${{cName}}, por aquí ${{mName}} tu mecánico de Chum, pasa que vamos un poco adelantados en la ruta de hoy y por lo mismo te queríamos preguntar si te sirve y puedes recibirnos unos ${{mins}} minutos antes? es decir aproximadamente a las ${{calculateNewTime(oTime, -mins)}}`;
            }} 
            else if (type === 'tarde') {{
                let mins = parseInt(document.getElementById('mins-tarde').value, 10);
                if (isNaN(mins) || mins <= 0) {{ alert('Ingresa un número válido.'); return; }}
                text = `Hola ${{cName}}, por aquí ${{mName}} tu mecánico de Chum, lo lamentamos muchisimo pero tenemos que comunicar un retraso de aproximadamente ${{mins}} minutos. Es posible para tí recibirnos, o prefieres que reagendemos o cancelemos?\\nLa hora prevista modificada en este momento es a las ${{calculateNewTime(oTime, mins)}}`;
            }}
            else if (type === 'llegue') {{
                let opt = document.querySelector('input[name="llegue_opt"]:checked').value;
                if(opt === 'normal') text = `Hola ${{cName}}, ya estamos en el lugar y listos para recibir la bicicleta`;
                else if(opt === 'avisar') text = `Hola ${{cName}}, ya estamos en el lugar para que le puedas avisar a la persona que nos traerá la bici`;
                else if(opt === 'porton') text = `Hola ${{cName}}, estamos ya en la entrada y te pedimos si nos puedes ayudar para que nos abran para pasar`;
                else if(opt === 'donde') text = `Hola ${{cName}}, estamos ya en el lugar y te queríamos preguntar si esperamos la bici en el estacionamiento o si vamos a conserjería o si a algun otro lugar?`;
            }}
            else if (type === 'listo') {{
                let opt = document.querySelector('input[name="listo_opt"]:checked').value;
                if(opt === 'buscar') text = `Hola ${{cName}}, ya tenemos tu bici lista para retirar acá en el taller móvil.`;
                else if(opt === 'proxima') text = `Hola ${{cName}}, ya terminamos la bici con que estábamos trabajando, nos pueden traer ahora la próxima?`;
                else if(opt === 'recibir') text = `Hola ${{cName}}, te cuento que ya estamos listos por acá y vamos camino a entregar la bici, para que nos puedan recibir.`;
                else if(opt === 'conserje') text = `Hola ${{cName}}, ya terminamos la misión y entregamos las bicis según acordado, acá va una foto de como quedaron entregadas! Pronto te estaremos enviando la nota de venta con los datos de pago y el detalle de lo realizado.`;
            }}

            window.open('https://wa.me/' + phone + '?text=' + encodeURIComponent(text), '_blank');
            closeWaModal();
        }}
    </script>
    """

    table_html = f"""
    <style>
        #mbs-table-container table tbody tr:nth-child(even) {{ background-color: #f8f9fa; }}
        #mbs-table-container table tbody tr:nth-child(odd) {{ background-color: #ffffff; }}
        .leaflet-bottom {{ bottom: 28% !important; }} 
        .leaflet-control-layers-list::before {{ content: 'Ruta'; display: block; margin-bottom: 5px; border-bottom: 1px solid #ccc; font-family:'Saturn-Bold'; font-size:14px; color:{CHUM_BLUE}; }} 
        .leaflet-control-layers-base {{ display: none; }}
        .leaflet-control-layers {{ border: 2px solid {CHUM_BLUE} !important; border-radius: 8px !important; color: {CHUM_BLUE} !important; font-family: 'Gotham', sans-serif; }}
    </style>
    <div id="mbs-table-container" style="position: fixed; bottom: 0; left: 0; width: 100%; height: 28%; background-color: white; z-index: 9999; overflow-y: auto; box-shadow: 0px -4px 10px rgba(0,0,0,0.1); border-top: 2px solid {CHUM_BLUE};">
        <table style="width: 100%; border-collapse: collapse; font-family: 'Gotham', sans-serif; font-size: 12px; font-weight: bold; table-layout: fixed;">
            <tbody>{table_rows_html}</tbody>
        </table>
    </div>
    {modal_html}
    {wa_modal_html}
    """
    js_filter = "<script>function autoFilter(){const p=new URLSearchParams(window.location.search);const m=p.get('mechanic');if(!m)return;const t=m.toLowerCase();const s=document.querySelectorAll('.leaflet-control-layers-selector');if(s.length===0){setTimeout(autoFilter,300);return}s.forEach(i=>{const l=i.nextElementSibling.innerText.trim().toLowerCase();if((l==='juan'||l==='seba')&&l!==t){if(i.checked)i.click()}})}window.addEventListener('load',autoFilter)</script>"

    m.get_root().html.add_child(folium.Element(table_html + js_filter))
    m.save("mechanic_route.html")

if __name__ == "__main__":
    generate_map()