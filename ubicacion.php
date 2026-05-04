<?php
// Force Santiago timezone for the math algorithm
date_default_timezone_set('America/Santiago');

// 1. The Secure Hash Algorithm (Hidden from the customer!)
function getHourlyToken($offsetHours = 0) {
    $timestamp = time() + ($offsetHours * 3600);
    // Format: YYYY-M-D-H (e.g., 2026-5-3-20)
    $str = date('Y-n-j-G', $timestamp);
    $hash = 0;
    
    for ($i = 0; $i < strlen($str); $i++) {
        $char = ord($str[$i]);
        $hash = ($hash * 31) + $char;
        // Force strict 32-bit signed integer matching (matches Javascript behavior)
        $hash = $hash & 0xFFFFFFFF;
        if ($hash > 0x7FFFFFFF) {
            $hash -= 0x100000000;
        }
    }
    return str_pad(abs($hash) % 10000, 4, '0', STR_PAD_LEFT);
}

// 2. Extract URL Parameter
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

// 3. SECURE MIDDLEMAN: If map is asking for coordinates, fetch from Firebase secretly
if (isset($_GET['ajax']) && $_GET['ajax'] == '1') {
    header('Content-Type: application/json');
    if (!$isValid) {
        echo json_encode(['error' => 'invalid']);
        exit;
    }
    
    // Server-side fetch (Customer never sees this URL)
    $firebaseUrl = 'https://vantracker-7cdef-default-rtdb.firebaseio.com/vans.json';
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $firebaseUrl);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
    curl_setopt($ch, CURLOPT_TIMEOUT, 5);
    $data = curl_exec($ch);
    curl_close($ch);

    $json = json_decode($data, true);
    $coords = null;
    if ($json) {
        foreach ($json as $dbName => $loc) {
            if (strtolower($dbName) === $targetMechanic) {
                $coords = $loc;
                break;
            }
        }
    }
    echo json_encode(['coords' => $coords]);
    exit;
}

// 4. GENERIC 404 ERROR (If token is wrong or expired)
if (!$isValid) {
    header("HTTP/1.0 404 Not Found");
    echo "<!DOCTYPE HTML PUBLIC \"-//IETF//DTD HTML 2.0//EN\">
<html><head>
<title>404 Not Found</title>
</head><body>
<h1>Not Found</h1>
<p>The requested URL was not found on this server.</p>
</body></html>";
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
        body, html { margin: 0; padding: 0; height: 100%; width: 100%; background: #f4f6f8; }
        #map { height: 100%; width: 100%; z-index: 1; }
    </style>
</head>
<body>

    <div id="map"></div>

    <script>
        // The frontend JS is completely dumb. It has no math, and no Firebase URL. 
        // It just asks the PHP file for the coordinates every 5 seconds.
        const targetMechanic = "<?php echo $targetMechanic; ?>";
        const secureParam = "<?php echo htmlspecialchars($rawParam); ?>";
        
        const map = L.map('map', { zoomControl: false }).setView([-33.452, -70.578], 15);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        let vanMarker = null;

        function fetchVanLocation() {
            // Ask our own secure PHP file for the location
            fetch(`ubicacion.php?ajax=1&mecanico=${secureParam}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error || !data.coords) return;
                    
                    let coords = data.coords;
                    let iconUrl = 'base_icon.png';
                    if (targetMechanic === 'seba') iconUrl = 'seba_icon.png';
                    if (targetMechanic === 'juan') iconUrl = 'juan_icon.png';
                    
                    if (!vanMarker) {
                        let vanIcon = L.icon({ iconUrl: iconUrl, iconSize: [40, 40], iconAnchor: [20, 20] });
                        vanMarker = L.marker([coords.lat, coords.lng], {icon: vanIcon}).addTo(map);
                        map.setView([coords.lat, coords.lng], 16); 
                    } else {
                        // Smoothly move marker
                        vanMarker.setLatLng([coords.lat, coords.lng]);
                    }
                })
                .catch(err => console.error("Error connecting to server."));
        }

        fetchVanLocation();
        setInterval(fetchVanLocation, 5000); 
    </script>
</body>
</html>