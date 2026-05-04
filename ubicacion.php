<?php
date_default_timezone_set('America/Santiago');

// ⚠️ PASTE YOUR ACTUAL GOOGLE MAPS API KEY HERE
$GMAPS_KEY = 'TU_CLAVE_API_AQUI';

function getHourlyToken($offsetHours = 0) {
    $timestamp = time() + ($offsetHours * 3600);
    $str = date('Y-n-j-G', $timestamp);
    $hash = 0;
    for ($i = 0; $i < strlen($str); $i++) {
        $char = ord($str[$i]);
        $hash = ($hash * 31) + $char;
        $hash = $hash & 0xFFFFFFFF;
        if ($hash > 0x7FFFFFFF) { $hash -= 0x100000000; }
    }
    return str_pad(abs($hash) % 10000, 4, '0', STR_PAD_LEFT);
}

$rawParam = isset($_GET['mecanico']) ? $_GET['mecanico'] : '';
$isValid = false;
$targetMechanic = '';

if (strlen($rawParam) > 4) {
    $urlToken = substr($rawParam, -4);
    $urlName = strtolower(substr($rawParam, 0, -4));
    $validCurrent = getHourlyToken(0);
    $validPrev = getHourlyToken(-1);
    if ($urlToken === $validCurrent || $urlToken === $validPrev) {
        $isValid = true;
        $targetMechanic = $urlName;
    }
}

if (isset($_GET['ajax']) && $_GET['ajax'] == 'coords') {
    header('Content-Type: application/json');
    if (!$isValid) { echo json_encode(['error' => 'invalid']); exit; }
    $firebaseUrl = 'https://vantracker-7cdef-default-rtdb.firebaseio.com/vans.json';
    $ch = curl_init(); curl_setopt($ch, CURLOPT_URL, $firebaseUrl); curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
    curl_setopt($ch, CURLOPT_TIMEOUT, 5); $data = curl_exec($ch); curl_close($ch);
    $json = json_decode($data, true);
    $coords = null;
    if ($json) {
        foreach ($json as $dbName => $loc) {
            if (strtolower($dbName) === $targetMechanic) { $coords = $loc; break; }
        }
    }
    echo json_encode(['coords' => $coords]); exit;
}

if (isset($_GET['ajax']) && $_GET['ajax'] == 'eta') {
    header('Content-Type: application/json');
    if (!$isValid) { echo json_encode(['error' => 'invalid']); exit; }
    $origin = $_GET['origin']; $dest = $_GET['dest'];
    $url = "https://maps.googleapis.com/maps/api/directions/json?origin={$origin}&destination={$dest}&departure_time=now&key={$GMAPS_KEY}";
    $ch = curl_init(); curl_setopt($ch, CURLOPT_URL, $url); curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
    curl_setopt($ch, CURLOPT_TIMEOUT, 10); $response = curl_exec($ch); curl_close($ch);
    echo $response; exit;
}

if (!$isValid) {
    header("HTTP/1.0 404 Not Found");
    echo "<!DOCTYPE HTML PUBLIC \"-//IETF//DTD HTML 2.0//EN\">\n<html><head>\n<title>404 Not Found</title>\n</head><body>\n<h1>Not Found</h1>\n<p>The requested URL was not found on this server.</p>\n</body></html>";
    exit;
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title> Aquí va tu taller Chum </title>
    <link rel="icon" type="image/x-icon" href="favicon.ico">
    <link rel="icon" type="image/png" sizes="32x32" href="favicon-32x32.png">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        @font-face { font-family: 'Saturn-Bold'; src: url('Saturn-Bold.woff') format('woff'); }
        @font-face { font-family: 'Gotham'; src: url('Gotham%20Bold.otf') format('opentype'); font-weight: bold; }
        body, html { margin: 0; padding: 0; height: 100%; width: 100%; background: #f4f6f8; font-family: 'Gotham', sans-serif; }
        #map { height: 100%; width: 100%; z-index: 1; }
        #eta-box {
            display: none; position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%);
            background: white; padding: 12px 25px; border-radius: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            z-index: 9999; border: 2px solid #011E41; text-align: center;
        }
        /* 🚨 THE TRANSPARENCY FIX */
        .leaflet-marker-icon { background: transparent !important; border: none !important; box-shadow: none !important; }
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="eta-box">
        <div style="font-size:11px; font-family:'Saturn-Bold', sans-serif; text-transform:lowercase; color:#8A9892; margin-bottom:2px;">llegada estimada</div>
        <div id="eta-time" style="font-size:22px; color:#011E41; font-weight:bold;">-- min</div>
    </div>
    <script>
        const targetMechanic = "<?php echo $targetMechanic; ?>";
        const secureParam = "<?php echo htmlspecialchars($rawParam); ?>";
        const urlParams = new URLSearchParams(window.location.search);
        const destLat = urlParams.get('lat');
        const destLng = urlParams.get('lng');
        const map = L.map('map', { zoomControl: false }).setView([-33.452, -70.578], 15);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        let vanMarker = null;
        let lastVanLat = null, lastVanLng = null;

        if (destLat && destLng) {
            document.getElementById('eta-box').style.display = 'block';
            L.marker([destLat, destLng], {
                icon: L.divIcon({html: '<div style="font-size:28px; line-height:28px; text-align:center;">🏠</div>', className: 'dest-pin', iconSize: [28,28], iconAnchor: [14,28]})
            }).addTo(map);
        }

        function fetchVanLocation() {
            fetch(`ubicacion.php?ajax=coords&mecanico=${secureParam}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error || !data.coords) return;
                    let coords = data.coords;
                    lastVanLat = coords.lat; lastVanLng = coords.lng;
                    
                    // ⚠️ Dynamic Icons with fallback
                    let iconUrl = 'base_icon.png';
                    if (targetMechanic === 'juan') iconUrl = 'icono_juan.png';
                    if (targetMechanic === 'seba') iconUrl = 'icono_seba.png';
                    
                    if (!vanMarker) {
                        let vanIcon = L.icon({ iconUrl: iconUrl, iconSize: [40, 40], iconAnchor: [20, 20] });
                        vanMarker = L.marker([coords.lat, coords.lng], {icon: vanIcon}).addTo(map);
                        if (destLat && destLng) {
                            map.fitBounds([ [coords.lat, coords.lng], [destLat, destLng] ], {padding: [50, 50]});
                        } else {
                            map.setView([coords.lat, coords.lng], 16); 
                        }
                        fetchETA();
                    } else {
                        vanMarker.setLatLng([coords.lat, coords.lng]);
                    }
                })
                .catch(err => console.error("Error connecting to server."));
        }

        function fetchETA() {
            if (!destLat || !destLng || !lastVanLat || !lastVanLng) return;
            fetch(`ubicacion.php?ajax=eta&mecanico=${secureParam}&origin=${lastVanLat},${lastVanLng}&dest=${destLat},${destLng}`)
                .then(r => r.json())
                .then(routeData => {
                    if(routeData.routes && routeData.routes.length > 0) {
                        let leg = routeData.routes[0].legs[0];
                        let durationSecs = leg.duration_in_traffic ? leg.duration_in_traffic.value : leg.duration.value;
                        let adjustedMins = Math.round((durationSecs * 1.07) / 60) + 3;
                        if(adjustedMins <= 1) { document.getElementById('eta-time').innerText = "¡Llegando!"; } 
                        else { document.getElementById('eta-time').innerText = adjustedMins + " min"; }
                    }
                }).catch(e => console.log("ETA check skipped"));
        }
        fetchVanLocation();
        setInterval(fetchVanLocation, 5000);
        setInterval(fetchETA, 90000);
    </script>
</body>
</html>