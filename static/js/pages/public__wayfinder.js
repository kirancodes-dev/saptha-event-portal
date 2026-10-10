/* Moved unchanged from an inline <script> in templates/public/wayfinder.html so the CSP
   needs no inline script (UPG-25). */
        // Setup coordinates inside L.CRS.Simple (Custom Coordinate Space)
        var map = L.map('map', {
            crs: L.CRS.Simple,
            minZoom: -1,
            maxZoom: 2,
            zoomSnap: 0.1
        });

        // Bounds of the map layout
        var bounds = [[0, 0], [600, 800]];
        map.fitBounds(bounds);
        map.setView([300, 400], 0);

        // Draw a simulated campus grid overlay
        var svgElement = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svgElement.setAttribute('xmlns', "http://www.w3.org/2000/svg");
        svgElement.setAttribute('viewBox', "0 0 800 600");
        svgElement.innerHTML = `
            <!-- Dark modern blueprint style college layout -->
            <rect width="800" height="600" fill="#090d16"/>
            <g opacity="0.1">
                <!-- Grid Lines -->
                <path d="M 0,100 L 800,100 M 0,200 L 800,200 M 0,300 L 800,300 M 0,400 L 800,400 M 0,500 L 800,500" stroke="#3b82f6" stroke-width="1"/>
                <path d="M 100,0 L 100,600 M 200,0 L 200,600 M 300,0 L 300,600 M 400,0 L 400,600 M 500,0 L 500,600 M 600,0 L 600,600 M 700,0 L 700,600" stroke="#3b82f6" stroke-width="1"/>
            </g>
            
            <!-- Campus Gardens & Outer Spaces -->
            <rect x="50" y="50" width="700" height="500" fill="none" stroke="#ffffff" stroke-width="2" stroke-opacity="0.15" rx="20"/>
            <rect x="550" y="350" width="160" height="160" fill="#10b981" fill-opacity="0.05" stroke="#10b981" stroke-width="1.5" stroke-dasharray="4,4" rx="10"/>
            <text x="630" y="440" fill="#10b981" fill-opacity="0.6" font-family='Outfit' font-size="12" text-anchor="middle">Green Zone Lawn</text>

            <!-- Buildings -->
            <!-- Main Block -->
            <rect x="300" y="70" width="200" height="100" fill="#1e293b" fill-opacity="0.8" stroke="#3b82f6" stroke-width="2" rx="8"/>
            <text x="400" y="125" fill="#f8fafc" font-family='Outfit' font-size="14" font-weight="bold" text-anchor="middle">Administration Block</text>

            <!-- CS & IT Building -->
            <rect x="100" y="240" width="180" height="110" fill="#1e293b" fill-opacity="0.8" stroke="#06b6d4" stroke-width="2" rx="8"/>
            <text x="190" y="300" fill="#f8fafc" font-family='Outfit' font-size="14" font-weight="bold" text-anchor="middle">Computer Science Labs</text>

            <!-- Seminar and Lecture Halls -->
            <rect x="500" y="220" width="200" height="100" fill="#1e293b" fill-opacity="0.8" stroke="#f59e0b" stroke-width="2" rx="8"/>
            <text x="600" y="275" fill="#f8fafc" font-family='Outfit' font-size="14" font-weight="bold" text-anchor="middle">Seminar Hall Block</text>

            <!-- Sports Stadium Arena -->
            <rect x="100" y="420" width="240" height="120" fill="#1e293b" fill-opacity="0.8" stroke="#10b981" stroke-width="2" rx="8"/>
            <text x="220" y="485" fill="#f8fafc" font-family='Outfit' font-size="14" font-weight="bold" text-anchor="middle">Sports Stadium Complex</text>

            <!-- Main Canteen / Food Court -->
            <rect x="520" y="400" width="100" height="80" fill="#1e293b" fill-opacity="0.8" stroke="#ec4899" stroke-width="2" rx="8"/>
            <text x="570" y="445" fill="#f8fafc" font-family='Outfit' font-size="11" font-weight="bold" text-anchor="middle">Food Court</text>

            <!-- Pathways / Roads (Main corridors) -->
            <path d="M 400,170 L 400,280 L 190,280 M 400,280 L 600,280 L 600,220 M 400,280 L 400,440 L 220,440 M 400,440 L 570,440 L 570,400 M 400,170 L 400,50" 
                  stroke="#ffffff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.1"/>
        `;

        var imageBounds = [[0, 0], [600, 800]];
        L.svgOverlay(svgElement, imageBounds).addTo(map);

        // Nodes for wayfinding calculation
        var nodes = {
            entrance: { name: "Main Entrance (Gate 1)", coords: [50, 400], icon: "fa-door-open", color: "#3b82f6" },
            lobby: { name: "Admin Block Lobby", coords: [150, 400], icon: "fa-building-columns", color: "#3b82f6" },
            canteen: { name: "Food Court / Cafeteria", coords: [420, 570], icon: "fa-utensils", color: "#ec4899" },
            seminar: { name: "Seminar Hall Block", coords: [270, 600], icon: "fa-chalkboard-user", color: "#f59e0b" },
            ground: { name: "Sports Arena Complex", coords: [470, 220], icon: "fa-running", color: "#10b981" },
            auditorium: { name: "Main Auditorium (Tech Fest Venue)", coords: [120, 350], icon: "fa-theater-masks", color: "#3b82f6" },
            lab1: { name: "Advanced CS Labs (Hackathon)", coords: [290, 190], icon: "fa-laptop-code", color: "#06b6d4" },
            lounge: { name: "Club Activities Lounge", coords: [270, 520], icon: "fa-comments", color: "#8b5cf6" }
        };

        // Graph connections (simplistic routes matching drawing coordinates)
        // Format of edges: [from, to, weight, route_description]
        var routes = {
            "entrance-lobby": { path: [[50, 400], [150, 400]], desc: "Walk straight from Gate 1 to the Administration Block Lobby." },
            "lobby-auditorium": { path: [[150, 400], [170, 400], [170, 350], [120, 350]], desc: "Head inside the Administration Block and turn left to the Main Auditorium entrance." },
            "lobby-lab1": { path: [[150, 400], [280, 400], [280, 190], [290, 190]], desc: "From the lobby, take the west pathway past the garden to the Computer Science Block, Labs are on the ground floor." },
            "lobby-seminar": { path: [[150, 400], [280, 400], [280, 600], [270, 600]], desc: "Take the east corridor from the lobby, walk towards the Seminar block entrance." },
            "lobby-ground": { path: [[150, 400], [280, 400], [280, 280], [440, 280], [440, 220], [470, 220]], desc: "Walk down the main central quad, pass the CS building, then head south to the Sports Stadium Complex." },
            "lobby-canteen": { path: [[150, 400], [280, 400], [280, 440], [440, 440], [440, 570], [420, 570]], desc: "Follow the central pathway past the CS lab block, turn left and walk directly to the open air Food Court." },
            "lobby-lounge": { path: [[150, 400], [280, 400], [280, 520], [270, 520]], desc: "Take the east path from the lobby towards the Seminar complex, lounge is on the ground floor lobby." }
        };

        // Complete the graph mapping dynamically for bidirectionality
        var fullGraph = {};
        function addEdge(u, v, path, desc) {
            if (!fullGraph[u]) fullGraph[u] = {};
            fullGraph[u][v] = { path: path, desc: desc };
            
            // Reverse path for bidirectional
            var revPath = [...path].reverse();
            if (!fullGraph[v]) fullGraph[v] = {};
            fullGraph[v][u] = { path: revPath, desc: desc.replace("from " + nodes[u].name, "from " + nodes[v].name).replace("to " + nodes[v].name, "to " + nodes[u].name) };
        }

        // Add predefined edges
        addEdge("entrance", "lobby", [[50, 400], [150, 400]], "Walk straight from Gate 1 to the Administration Block Lobby.");
        addEdge("lobby", "auditorium", [[150, 400], [170, 400], [170, 350], [120, 350]], "Walk into the Administration Block lobby and turn left into the Main Auditorium foyer.");
        addEdge("lobby", "lab1", [[150, 400], [280, 400], [280, 190], [290, 190]], "Exit the Lobby west door, walk past the fountain, enter the CS Block.");
        addEdge("lobby", "seminar", [[150, 400], [280, 400], [280, 600], [270, 600]], "Exit the Lobby east corridor, follow the yellow tiles to the Seminar Hall Block.");
        addEdge("lobby", "ground", [[150, 400], [280, 400], [280, 220], [470, 220]], "Walk down the main west walkway, turn left at the sports ground gates.");
        addEdge("lobby", "canteen", [[150, 400], [280, 400], [280, 440], [420, 570]], "Walk down the main central avenue, the Food Court is right beside the sports field.");
        addEdge("lobby", "lounge", [[150, 400], [280, 400], [280, 520], [270, 520]], "Walk down the east passage towards Seminar block, the Club Lounge is on your right.");
        
        // Connect others via lobby transit if not direct
        // Standard Dijkstra parser (simplified since they all connect through lobby transit)
        function findShortestRoute(start, end) {
            if (start === end) return { path: [nodes[start].coords], steps: ["You are already at your destination."] };
            
            // If direct link exists
            if (fullGraph[start] && fullGraph[start][end]) {
                return { 
                    path: fullGraph[start][end].path, 
                    steps: [fullGraph[start][end].desc] 
                };
            }
            
            // Otherwise go through lobby
            if (fullGraph[start] && fullGraph[start]["lobby"] && fullGraph["lobby"][end]) {
                var p1 = fullGraph[start]["lobby"];
                var p2 = fullGraph["lobby"][end];
                var combinedPath = [...p1.path];
                // Avoid duplicating the lobby coordinate [150, 400]
                combinedPath.pop();
                combinedPath.push(...p2.path);
                return {
                    path: combinedPath,
                    steps: [p1.desc, "Reach Admin Lobby, then transit:", p2.desc]
                };
            }
            
            // Default fallback
            return {
                path: [nodes[start].coords, nodes[end].coords],
                steps: ["Take the general campus pathways from " + nodes[start].name + " to " + nodes[end].name + "."]
            };
        }

        // Render Markers
        var markers = {};
        Object.keys(nodes).forEach(key => {
            var n = nodes[key];
            var iconHtml = `<div style="background: ${escapeHtml(n.color)}; width:36px; height:36px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; border: 2px solid rgba(255,255,255,0.4); box-shadow: 0 4px 8px rgba(0,0,0,0.4)">
                                <i class="fas ${escapeHtml(n.icon)}"></i>
                            </div>`;
            var myIcon = L.divIcon({
                html: iconHtml,
                className: 'custom-div-icon',
                iconSize: [36, 36],
                iconAnchor: [18, 18],
                popupAnchor: [0, -18]
            });

            var m = L.marker(n.coords, { icon: myIcon }).addTo(map);
            m.bindPopup(`<div class="text-center">
                            <h6 class="fw-bold m-0 text-white">${escapeHtml(n.name)}</h6>
                            <span class="text-muted small">Campus Landmark</span>
                            <hr class="my-1 border-secondary">
                            <button data-h-click="se:call" data-call="setAsDestination" data-args="${escapeHtml(JSON.stringify([key]))}" class="btn btn-primary btn-xs py-1 px-2 rounded mt-1" style="font-size:11px;">Navigate Here</button>
                         </div>`);
            markers[key] = m;
        });

        // Zoom to marker helper
        function zoomToVenue(key) {
            var coords = nodes[key].coords;
            map.setView(coords, 1);
            markers[key].openPopup();
            document.getElementById('end-node').value = key;
        }

        function setAsDestination(key) {
            document.getElementById('end-node').value = key;
            map.closePopup();
            drawActiveRoute();
        }

        var activePolyline = null;
        var startMarkerGlow = null;
        var endMarkerGlow = null;

        function drawActiveRoute() {
            var startKey = document.getElementById('start-node').value;
            var endKey = document.getElementById('end-node').value;

            // Remove existing route drawings
            if (activePolyline) {
                map.removeLayer(activePolyline);
            }
            if (startMarkerGlow) map.removeLayer(startMarkerGlow);
            if (endMarkerGlow) map.removeLayer(endMarkerGlow);

            var routeData = findShortestRoute(startKey, endKey);

            // Draw beautiful glowing dynamic dashed path
            activePolyline = L.polyline(routeData.path, {
                color: '#3b82f6',
                weight: 6,
                opacity: 0.8,
                lineJoin: 'round',
                className: 'direction-arrow-animation'
            }).addTo(map);

            // Add terminal visual enhancements (start/end indicators)
            startMarkerGlow = L.circle(nodes[startKey].coords, {
                color: '#3b82f6',
                fillColor: '#3b82f6',
                fillOpacity: 0.2,
                radius: 20
            }).addTo(map);

            endMarkerGlow = L.circle(nodes[endKey].coords, {
                color: '#10b981',
                fillColor: '#10b981',
                fillOpacity: 0.2,
                radius: 25
            }).addTo(map);

            // Fit map bounds to show full route with padding
            map.fitBounds(activePolyline.getBounds(), { padding: [50, 50] });

            // Display instructions panel
            var instContainer = document.getElementById('instructions-container');
            var instContent = document.getElementById('instructions-content');
            instContainer.classList.remove('d-none');
            
            instContent.innerHTML = routeData.steps.map((step, idx) => {
                return `<div class="d-flex align-items-start gap-2 mb-2">
                            <span class="badge bg-secondary rounded-pill mt-1" style="font-size: 9px;">${escapeHtml(idx + 1)}</span>
                            <span class="text-light">${escapeHtml(step)}</span>
                        </div>`;
            }).join('');
        }

        // Wire Event Listeners
        document.getElementById('get-directions').addEventListener('click', drawActiveRoute);
        
        // Auto draw on load
        window.addEventListener('load', function() {
            setTimeout(drawActiveRoute, 500);
        });
    
