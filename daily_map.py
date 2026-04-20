import os
import re
import requests
import googlemaps
import folium
import urllib.parse
from datetime import datetime, timedelta
import pytz
from icalendar import Calendar

# --- 1. CONFIGURATION ---
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

SERVICE_MAP = {
    "Armado de Bicicleta a Domicilio Con Cambios": "ARC",
    "Armado de Bicicleta a Domicilio Sin Cambios": "ARS",
    "Armado de Bicicleta a Domicilio Armado con Optimizado": "ARO",
    "Armado de Bicicleta a Domicilio Armado Bici Eléctrica Rigida": "ARE",
    "Armado de Bicicleta a Domicilio Con Retráctil y/o Bloqueo Remoto": "ARB",
    "Cambio de Juego de Dirección o Horquilla Cambio de Horquilla": "DIR",
    "Cambio de Juego de Dirección o Horquilla Cambio de Direccion": "DIR",
    "Conversion a Tubeless 1 Rueda": "TUB",
    "Mantencion Clasica de Bicicleta Mant. Clasica 1 Bici": "CL1",
    "Mantención de Bicicleta a Domicilio Mantencion Preventiva 1 Bici": "PR1",
    "Mantención de Bicicleta a Domicilio Mantencion Clasica 1 Bici": "CL1",
    "Mantención de Bicicleta a Domicilio Mantencion Profunda 1 Bici": "PF1",
    "Mantención de Bicicleta Electrica Mant. Electrica Rigida": "ELR",
    "Mantención de Bicicleta Electrica Mant. Elect. Doble Susp.": "ELD",
    "Mantencion de Bicicleta Ruta Aero o de Triatlón 1 Bicicleta": "TR1",
    "Visita Mecanica": "VM",
}

CARD_STYLE = (
    "font-family: 'Helvetica', sans-serif; font-size: 11px; font-weight: bold; "
    "background-color: white; padding: 5px 10px; border-radius: 8px; "
    "box-shadow: 0px 3px 8px rgba(0,0,0,0.15); white-space: nowrap; "
    "display: inline-flex; align-items: center; border: none;"
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
                    if not isinstance(start_dt, datetime):
                        start_dt = timezone.localize(datetime.combine(start_dt, datetime.min.time())).replace(hour=9)
                    else:
                        start_dt = start_dt.astimezone(timezone)

                    if start_dt.date() == today:
                        summary = str(component.get('summary', ''))
                        desc = str(component.get('description', ''))
                        name_match = re.search(r'Cliente:\s*(.*?)\s*\(', desc)
                        extracted_name = name_match.group(1).strip() if name_match else summary.split(',')[0]
                        
                        parts = re.split(r'\s*\d+x\s+', summary, maxsplit=1, flags=re.IGNORECASE)
                        
                        if len(parts) == 2:
                            clean_addr = parts[0].strip().rstrip(',').strip()
                            clean_svc = parts[1].strip()
                        else:
                            clean_addr = summary.split(',')[0].strip()
                            clean_svc = summary.strip()
                            
                        abbrev = SERVICE_MAP.get(clean_svc, "SRV") 
                        
                        all_appointments.append({
                            'name': extracted_name, 
                            'address': clean_addr, 
                            'service': clean_svc, 
                            'mechanic': name, 
                            'start_dt': start_dt, 
                            'abbrev': abbrev
                        })
        except Exception as e: print(f"Error: {e}")
    return all_appointments

def generate_map():
    appointments = get_appointments()
    if not appointments: return

    m = folium.Map(location=BASE_LOCATION, zoom_start=13, tiles=None)
    folium.TileLayer('cartodbpositron', control=False).add_to(m)
    folium.Marker(location=BASE_LOCATION, icon=folium.Icon(color='black', icon='home')).add_to(m)
    
    all_points_for_zoom = [BASE_LOCATION]
    table_rows_html = ""

    ordered_mechs = ['Juan', 'Seba']
    
    for name in ordered_mechs:
        info = MECHANICS[name]
        fg = folium.FeatureGroup(name=name).add_to(m)
        mech_apps = sorted([a for a in appointments if a['mechanic'] == name], key=lambda x: x['start_dt'])
        current_loc = f"{BASE_LOCATION[0]}, {BASE_LOCATION[1]}"
        
        for i, app in enumerate(mech_apps):
            label_id = f"{info['initial']}{i+1}"
            leg_color = info['palette'][i % len(info['palette'])]
            
            directions = gmaps.directions(current_loc, app['address'], mode="driving", arrival_time=app['start_dt'])
            if directions:
                leg = directions[0]['legs'][0]
                raw_seconds = leg.get('duration_in_traffic', leg['duration'])['value']
                buffered_mins = round((raw_seconds * 1.07) / 60)
                departure_dt = app['start_dt'] - timedelta(seconds=raw_seconds * 1.07)
                
                raw_pts = [(p['lat'], p['lng']) for p in googlemaps.convert.decode_polyline(directions[0]['overview_polyline']['points'])]
                all_points_for_zoom.extend(raw_pts)
                points = apply_offset(raw_pts, info['offset'])
                folium.PolyLine(points, color=leg_color, weight=6, opacity=0.85).add_to(fg)

                mid = points[len(points)//2]
                waze_link = f"https://waze.com/ul?ll={leg['end_location']['lat']},{leg['end_location']['lng']}&navigate=yes"
                folium.Marker(location=mid, icon=folium.DivIcon(html=f'''<a href="{waze_link}" target="_blank" style="text-decoration:none;"><div style="{CARD_STYLE} color:{leg_color}; transform:translateY(-20px);"><img src="{WAZE_ICON_URL}" style="width:16px; margin-right:5px;">{label_id} / {departure_dt.strftime('%H:%M')} / {buffered_mins} min</div></a>''')).add_to(fg)

                end_pt = apply_offset([(leg['end_location']['lat'], leg['end_location']['lng'])], info['offset'])[0]
                folium.Marker(location=end_pt, icon=folium.DivIcon(html=f'<div style="{CARD_STYLE} color:black; transform:translate(-10%, -50%); pointer-events:none;">{app["start_dt"].strftime("%H:%M")} {app["name"]} ({label_id}) {app["abbrev"]}</div>')).add_to(fg)
                
                # --- NEW COMPACT, ONE-LINE TABLE UI ---
                # Added 'max-width: 0' and 'text-overflow: ellipsis' to force text to fit available % width.
                table_rows_html += f"""
                <tr style="border-bottom: 1px solid #eee; height: 26px;">
                    <td style="padding: 4px 6px; color: {leg_color}; width: 6%; white-space: nowrap;">{label_id}</td>
                    <td style="padding: 4px 6px; width: 10%; white-space: nowrap;">{app['start_dt'].strftime('%H:%M')}</td>
                    <td style="padding: 4px 6px; width: 28%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 0;">{app['name']}</td>
                    <td style="padding: 4px 6px; font-size: 10px; color: #666; width: 46%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 0;">{app['address']}</td>
                    <td style="padding: 4px 6px; font-size: 10px; color: #444; width: 10%; white-space: nowrap; text-align: right;">{app['abbrev']}</td>
                </tr>
                """
                current_loc = app['address']

    folium.LayerControl(collapsed=False).add_to(m)

    if all_points_for_zoom:
        lats, lngs = zip(*all_points_for_zoom)
        sw, ne = [min(lats), min(lngs)], [max(lats), max(lngs)]
        height = ne[0] - sw[0]
        sw_phantom = [sw[0] - (height * 0.45), sw[1]]
        m.fit_bounds([sw_phantom, ne])

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
    
    # Simple JS: ONLY reads URL parameters to auto-click the map layers. Does NOT touch the table rows.
    js_filter = "<script>function autoFilter(){const p=new URLSearchParams(window.location.search);const m=p.get('mechanic');if(!m)return;const t=m.toLowerCase();const s=document.querySelectorAll('.leaflet-control-layers-selector');if(s.length===0){setTimeout(autoFilter,300);return}s.forEach(i=>{const l=i.nextElementSibling.innerText.trim().toLowerCase();if((l==='juan'||l==='seba')&&l!==t){if(i.checked)i.click()}})}window.addEventListener('load',autoFilter)</script>"

    m.get_root().html.add_child(folium.Element(table_html + js_filter))
    m.save("mechanic_route.html")

if __name__ == "__main__":
    generate_map()