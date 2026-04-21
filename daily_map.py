import os
import re
import requests
import googlemaps
import folium
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar

GMAPS_KEY = os.getenv('GMAPS_API_KEY')
gmaps = googlemaps.Client(key=GMAPS_KEY)
timezone = pytz.timezone('America/Santiago')

BASE_LOCATION = [-33.45219480797122, -70.5787333882418] 
CALENDAR_URL = 'https://calendar.google.com/calendar/ical/c_0e3e9c70ab1527edfef805c43e9fd06dabb0fdfab8e5081f4feb40565337708b%40group.calendar.google.com/private-a534c46e66604fef2e96a3dc4810f688/basic.ics'
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
debug_log = ""

def apply_offset(points, offset_tuple, multiplier=1):
    return [(p[0] + (offset_tuple[0] * multiplier), p[1] + (offset_tuple[1] * multiplier)) for p in points]

def extract_var(text, key):
    pattern = rf'(?i){key}[:\s]*([^\n\r]+)'
    match = re.search(pattern, text)
    if match: return re.sub(r'<[^>]+>', '', match.group(1)).strip()
    return ""

def get_appointments():
    global debug_log
    all_appointments = []
    
    now_dt = datetime.now(timezone)
    if now_dt.hour >= 18: target_date = (now_dt + timedelta(days=1)).date()
    else: target_date = now_dt.date()
    
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

                if start_dt.date() == target_date:
                    raw_desc = str(component.get('description', ''))
                    summary = str(component.get('summary', ''))
                    
                    clean_desc = raw_desc.replace('\\n', '\n').replace('\\N', '\n').replace('&nbsp;', ' ')
                    clean_desc = re.sub(r'<[^>]+>', '\n', clean_desc) 
                    
                    debug_log += f"<br><b>RAW TEXT SEEN:</b><br>{summary}<br>{clean_desc}<hr>"
                    
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

                    desc_lower = clean_desc.lower()
                    sum_lower = summary.lower()
                    
                    if "sebadechum" in desc_lower or "sebadechum" in sum_lower: mechanic_name = "Seba"
                    elif "juandechum" in desc_lower or "juandechum" in sum_lower: mechanic_name = "Juan"
                    else: continue 

                    abbrev = "SRV" 
                    clean_svc_lower = servicio.lower()
                    for dictionary_key, code in sorted(SERVICE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
                        if dictionary_key.lower() in clean_svc_lower:
                            abbrev = code
                            break
                            
                    full_route_address = f"{address1}, {comuna}, Santiago, Chile".strip(', ')
                    
                    all_appointments.append({
                        'name': cliente, 'address1': address1, 'address2': address2, 'comuna': comuna,
                        'route_address': full_route_address, 'service': servicio, 
                        'mechanic': mechanic_name, 'start_dt': start_dt, 'abbrev': abbrev
                    })
    except Exception as e: print(f"Error: {e}")
    return all_appointments

def generate_map():
    global debug_log
    appointments = get_appointments()

    m = folium.Map(location=BASE_LOCATION, zoom_start=13, tiles=None)
    folium.TileLayer('cartodbpositron', control=False).add_to(m)
    folium.Marker(location=BASE_LOCATION, icon=folium.Icon(color='black', icon='home')).add_to(m)
    
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
                waze_link = f"https://waze.com/ul?ll={leg['end_location']['lat']},{leg['end_location']['lng']}&navigate=yes"
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:{leg_color}; transform:translateY(-20px);"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{label_id} / {departure_dt.strftime('%H:%M')} / {buffered_mins} min</div></a>''')).add_to(fg)

                short_cust_name = app['name'][:20]
                display_addr1 = app['address1'][:20] + "..." if len(app['address1']) > 20 else app['address1']
                end_pt = apply_offset([(leg['end_location']['lat'], leg['end_location']['lng'])], info['offset'])[0]
                folium.Marker(location=end_pt, icon=folium.DivIcon(html=f'<div style="{CARD_STYLE} color:black; transform:translate(-10%, -50%); pointer-events:none;">{app["start_dt"].strftime("%H:%M")} / {short_cust_name} / {display_addr1} / {app["abbrev"]}</div>')).add_to(fg)
                
                table_address = f"{app['address1']} {app['address2']} {app['comuna']}".strip()
                
                table_rows_html += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 4px 2px; color: {leg_color}; width: 6%; white-space: nowrap; vertical-align: middle;">{label_id}</td>
                    <td style="padding: 4px 2px; width: 10%; white-space: nowrap; vertical-align: middle;">{app['start_dt'].strftime('%H:%M')}</td>
                    <td style="padding: 4px 2px; width: 23%; font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 0; vertical-align: middle;">{short_cust_name}</td>
                    <td style="padding: 4px 2px; width: 51%; font-size: 10px; color: #666; white-space: normal; line-height: 1.1; vertical-align: middle;">{table_address}</td>
                    <td style="padding: 4px 2px; font-size: 10px; color: #444; width: 10%; white-space: nowrap; text-align: right; vertical-align: middle;">{app['abbrev']}</td>
                </tr>
                """
                current_loc = app['route_address']

        # --- RETURN TO BASE LOGIC ---
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
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:#666; transform:translateY(-20px);"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">Base / {buffered_mins} min</div></a>''')).add_to(fg)


    folium.LayerControl(collapsed=False).add_to(m)

    if len(all_points_for_zoom) > 1:
        lats, lngs = zip(*all_points_for_zoom)
        sw, ne = [min(lats), min(lngs)], [max(lats), max(lngs)]
        height = ne[0] - sw[0]
        sw_phantom = [sw[0] - (height * 0.45), sw[1]]
        m.fit_bounds([sw_phantom, ne])

    if not table_rows_html:
        table_rows_html = f'<tr><td colspan="5" style="text-align:left; padding: 10px; font-weight:normal; font-size:10px;"><b>ERROR - SIN RUTAS. DIAGNOSTICO:</b><br>{debug_log}</td></tr>'

    table_html = f"""
    <div id="mbs-table-container" style="
        position: fixed; bottom: 0; left: 0; width: 100%; height: 28%;
        background-color: white; z-index: 9999; overflow-y: auto;
        box-shadow: 0px -4px 10px rgba(0,0,0,0.1); border-top: 2px solid #ddd;">
        <table style="width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 12px; font-weight: bold; table-layout: fixed;">
            <tbody>
                {table_rows_html}
            </tbody>
        </table>
    </div>
    <style>
        .leaflet-bottom {{ bottom: 28% !important; }}
        .leaflet-control-layers-list::before {{ content: 'Ruta'; display: block; font-weight: bold; margin-bottom: 5px; border-bottom: 1px solid #ccc; }}
        .leaflet-control-layers-base {{ display: none; }}
    </style>
    """
    
    js_filter = "<script>function autoFilter(){const p=new URLSearchParams(window.location.search);const m=p.get('mechanic');if(!m)return;const t=m.toLowerCase();const s=document.querySelectorAll('.leaflet-control-layers-selector');if(s.length===0){setTimeout(autoFilter,300);return}s.forEach(i=>{const l=i.nextElementSibling.innerText.trim().toLowerCase();if((l==='juan'||l==='seba')&&l!==t){if(i.checked)i.click()}})}window.addEventListener('load',autoFilter)</script>"

    m.get_root().html.add_child(folium.Element(table_html + js_filter))
    m.save("mechanic_route.html")

if __name__ == "__main__":
    generate_map()