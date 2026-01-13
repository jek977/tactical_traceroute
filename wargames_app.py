import platform
import subprocess
import re
import socket
import requests
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# --- BACKEND LOGIC ---


def get_location(ip):
    try:
        # Using ip-api.com for geolocation
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        data = response.json()
        if data["status"] == "success":
            return {
                "lat": data["lat"],
                "lon": data["lon"],
                "country": data["countryCode"],
                "city": data.get("city", "Unknown"),
                "ip": ip,
            }
    except Exception:
        pass
    return None


def run_traceroute(target):
    os_name = platform.system().lower()
    # Adjust command based on OS
    if "windows" in os_name:
        cmd = ["tracert", "-d", "-h", "15", "-w", "500", target]
    else:
        cmd = ["traceroute", "-n", "-m", "15", "-w", "1", target]

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, _ = process.communicate()
        ip_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        found_ips = []
        for line in stdout.splitlines():
            match = ip_pattern.search(line)
            if match:
                ip = match.group()
                # Filter out local loops
                if ip not in found_ips and not ip.startswith("127."):
                    found_ips.append(ip)
        return found_ips
    except Exception:
        return []


# --- FRONTEND TEMPLATE ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NORAD // GLOBAL_NETWORK_COMMAND</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script src="https://unpkg.com/topojson@3"></script>
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --neon: #00ffff; --warn: #ffaa00; --alert: #ff0033; --highlight: #ffffff; }
        body { background: #000; color: var(--neon); font-family: 'Share Tech Mono', monospace; overflow: hidden; margin: 0; text-transform: uppercase; }
        .container { display: flex; height: 100vh; border: 4px double var(--neon); box-sizing: border-box; }
        
        .map-panel { flex: 2.5; position: relative; border-right: 2px solid var(--neon); background: #050505; cursor: grab; }
        .map-panel:active { cursor: grabbing; }

        .controls-panel { flex: 1.2; padding: 15px; background: #000; display: flex; flex-direction: column; overflow: hidden; }
        
        input { background: #000; border: 1px solid var(--neon); color: #f0f; padding: 10px; width: 100%; box-sizing: border-box; font-family: inherit; font-size: 1.1rem; outline: none; margin-bottom: 10px;}
        
        .btn-row { display: flex; gap: 10px; }
        button { background: var(--neon); border: none; color: #000; padding: 10px; cursor: pointer; font-weight: bold; flex: 1; transition: 0.2s; }
        button:hover { background: #fff; box-shadow: 0 0 10px #fff; }
        button#resetBtn { background: #333; color: var(--neon); border: 1px solid var(--neon); }

        .terminal-header { color: var(--warn); border-bottom: 1px solid var(--warn); margin-top: 20px; font-size: 0.9rem; padding-bottom: 5px; }
        #consoleLog { flex-grow: 1; border: 1px solid rgba(0,255,255,0.2); margin-top: 5px; padding: 10px; font-size: 0.85rem; overflow-y: auto; color: #0f0; background: rgba(0,10,10,0.5); }
        
        .hop-entry { margin-bottom: 5px; border-bottom: 1px solid rgba(0,255,0,0.1); padding: 5px; cursor: crosshair; transition: all 0.2s; }
        .hop-entry.active-log { background: rgba(0, 255, 255, 0.3); color: var(--highlight); border-left: 5px solid var(--highlight); }
        
        path.country { fill: #000; stroke: var(--neon); stroke-width: 0.5; opacity: 0.6; }
        .trace-arc { fill: none; stroke-width: 2; stroke-dasharray: 1000; stroke-dashoffset: 1000; animation: draw 2s forwards linear; }
        
        .node { fill: #f0f; stroke: #fff; stroke-width: 1; transition: all 0.3s; cursor: crosshair; }
        .node.active-node { fill: var(--highlight) !important; r: 12 !important; stroke-width: 3; filter: drop-shadow(0 0 15px #fff); }

        @keyframes draw { to { stroke-dashoffset: 0; } }

        .overlay { pointer-events: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
                    background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.1) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.01), rgba(0, 255, 0, 0.005), rgba(0, 0, 255, 0.01));
                    background-size: 100% 3px, 3px 100%; z-index: 100; }
    </style>
</head>
<body>
<div class="overlay"></div>
<div class="container">
    <div class="map-panel" id="map"></div>
    <div class="controls-panel">
        <h2 style="margin:0; color:var(--warn)">STRATEGIC COMMAND</h2>
        <input type="text" id="target" value="google.com" onfocus="this.value=''">
        <div class="btn-row">
            <button id="traceBtn" onclick="startTrace()">INITIATE SCAN</button>
            <button id="resetBtn" onclick="resetView()">RESET VIEW</button>
        </div>

        <div class="terminal-header">NETWORK_NODES</div>
        <div id="consoleLog">
            <div class="hop-entry">> READY FOR COMMAND.</div>
        </div>
    </div>
</div>

<script>
    const mapDiv = document.getElementById('map');
    const width = mapDiv.clientWidth;
    const height = mapDiv.clientHeight;
    
    const svg = d3.select("#map").append("svg").attr("width", "100%").attr("height", "100%");
    const g = svg.append("g");

    const zoom = d3.zoom()
        .scaleExtent([1, 25])
        .on("zoom", (event) => { g.attr("transform", event.transform); });

    svg.call(zoom);

    // Initial Polar-aligned projection
    const projection = d3.geoMercator()
        .scale(width/6.5)
        .translate([width/2, (height/2) + 50]);

    const path = d3.geoPath().projection(projection);

    d3.json("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json").then(data => {
        g.selectAll("path")
            .data(topojson.feature(data, data.objects.countries).features)
            .enter().append("path").attr("class", "country").attr("d", path);
    });

    function calcDistance(lat1, lon1, lat2, lon2) {
        const R = 6371; 
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                  Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                  Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    function resetView() {
        svg.transition().duration(750).call(zoom.transform, d3.zoomIdentity);
    }

    function fitToNodes(nodes) {
        if (nodes.length === 0) return;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        nodes.forEach(n => {
            const p = projection([n.lon, n.lat]);
            if (p[0] < minX) minX = p[0]; if (p[1] < minY) minY = p[1];
            if (p[0] > maxX) maxX = p[0]; if (p[1] > maxY) maxY = p[1];
        });
        const padding = 100;
        const scale = Math.min(width / ((maxX - minX) + padding * 2), height / ((maxY - minY) + padding * 2));
        const transform = d3.zoomIdentity.translate(width/2, height/2).scale(scale).translate(-(minX+maxX)/2, -(minY+maxY)/2);
        svg.transition().duration(1500).ease(d3.easeCubicInOut).call(zoom.transform, transform);
    }

    function highlight(index, state) {
        d3.select(`#node-${index}`).classed('active-node', state);
        const logItem = document.getElementById(`log-item-${index}`);
        if (logItem) logItem.classList.toggle('active-log', state);
    }

    async function startTrace() {
        const target = document.getElementById('target').value;
        const log = document.getElementById('consoleLog');
        const btn = document.getElementById('traceBtn');
        
        g.selectAll(".trace-arc").remove();
        g.selectAll(".node").remove();
        log.innerHTML = `<div class="hop-entry" style="color:var(--warn)">> PURGING LOCAL CACHE...</div>`;
        
        setTimeout(() => {
            log.innerHTML += `<div class="hop-entry">> GATHERING DATA...</div>`;
            log.scrollTop = log.scrollHeight;
        }, 400);

        btn.disabled = true;

        try {
            const response = await fetch('/trace_route', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({target: target})
            });
            const data = await response.json();
            
            log.innerHTML = "";
            let totalDistKm = 0;
            let uniqueCountries = new Set();

            data.hops.forEach((h, i) => {
                uniqueCountries.add(h.country);
                const entry = document.createElement('div');
                entry.className = 'hop-entry';
                entry.id = `log-item-${i}`;
                entry.onmouseenter = () => highlight(i, true);
                entry.onmouseleave = () => highlight(i, false);
                entry.innerHTML = `<span class="hop-num">[${i+1}]</span> ${h.ip}<br><small>LOC: ${h.city}, ${h.country}</small>`;
                log.appendChild(entry);

                const p2 = projection([h.lon, h.lat]);

                if (i > 0) {
                    const hPrev = data.hops[i-1];
                    totalDistKm += calcDistance(hPrev.lat, hPrev.lon, h.lat, h.lon);
                    const p1 = projection([hPrev.lon, hPrev.lat]);
                    const dx = p2[0] - p1[0], dy = p2[1] - p1[1];
                    const dr = Math.sqrt(dx * dx + dy * dy) * 1.2;
                    const color = h.country !== hPrev.country ? "var(--alert)" : "var(--neon)";
                    const arcPath = `M${p1[0]},${p1[1]} A${dr},${dr} 0 0,1 ${p2[0]},${p2[1]}`;
                    g.append("path").attr("class", "trace-arc").attr("d", arcPath).attr("stroke", color);
                }

                g.append("circle")
                    .attr("id", `node-${i}`)
                    .attr("class", "node")
                    .attr("cx", p2[0]).attr("cy", p2[1]).attr("r", 5)
                    .on("mouseover", () => highlight(i, true))
                    .on("mouseout", () => highlight(i, false));
            });

            if (data.hops.length > 0) {
                const totalDistMiles = totalDistKm * 0.621371;
                log.innerHTML += `
                    <div class="hop-entry" style="border-top: 2px solid var(--warn); margin-top: 15px; color: var(--warn); font-size: 0.9rem;">
                        > TRACE COMPLETED<br>
                        > TOTAL POINTS: ${data.hops.length}<br>
                        > COUNTRIES: ${uniqueCountries.size}<br>
                        > DISTANCE: ${totalDistKm.toFixed(2)} KM / ${totalDistMiles.toFixed(2)} MILES
                    </div>`;
                log.scrollTop = log.scrollHeight;
                fitToNodes(data.hops);
            }

        } catch (err) {
            log.innerHTML += `<div class="hop-entry" style="color:red">> ACCESS DENIED</div>`;
        }
        btn.disabled = false;
    }
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---


@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)


@app.route("/trace_route", methods=["POST"])
def trace():
    target = request.json.get("target")
    raw_ips = run_traceroute(target)
    hops = [get_location(ip) for ip in raw_ips]
    return jsonify({"hops": [h for h in hops if h]})


if __name__ == "__main__":
    # Setting use_reloader=False can sometimes help in terminal environments
    app.run(debug=True, port=5000)
