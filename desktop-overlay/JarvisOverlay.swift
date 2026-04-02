import Cocoa
import WebKit
import CoreGraphics

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var webView: WKWebView?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let screenFrame = screen.frame

        let windowSize = CGSize(width: 300, height: 300)
        // Position in bottom-right corner with padding
        let padding: CGFloat = 40
        let windowFrame = CGRect(
            x: screenFrame.width - windowSize.width - padding,
            y: padding,
            width: windowSize.width,
            height: windowSize.height
        )

        window = NSWindow(
            contentRect: windowFrame,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )

        guard let window = window else { return }

        window.isOpaque = false
        window.backgroundColor = NSColor.clear
        // Place window above all normal windows (floating overlay)
        let floatingLevel = Int(CGWindowLevelForKey(.floatingWindow))
        window.level = NSWindow.Level(rawValue: floatingLevel)
        window.ignoresMouseEvents = true
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]

        let webViewConfig = WKWebViewConfiguration()
        // No file access needed; HTML is loaded inline via loadHTMLString

        webView = WKWebView(frame: window.contentView?.bounds ?? .zero, configuration: webViewConfig)
        guard let webView = webView else { return }

        // Make WKWebView fully transparent on macOS
        // WKWebView does not have .backgroundColor on macOS; use layer + underPageBackgroundColor
        webView.wantsLayer = true
        webView.layer?.backgroundColor = NSColor.clear.cgColor

        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = .clear
        }
        webView.setValue(false, forKey: "drawsBackground")

        window.contentView = webView

        let htmlContent = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>JARVIS Overlay</title>
            <style>
                body, html {
                    margin: 0;
                    padding: 0;
                    width: 100%;
                    height: 100%;
                    background: transparent;
                    overflow: hidden;
                }
                canvas {
                    display: block;
                    width: 100%;
                    height: 100%;
                }
            </style>
        </head>
        <body>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
            <script>

                // Scene setup
                const scene = new THREE.Scene();
                const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
                const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
                renderer.setSize(window.innerWidth, window.innerHeight);
                renderer.setClearColor(0x000000, 0);
                renderer.shadowMap.enabled = true;
                document.body.appendChild(renderer.domElement);

                camera.position.z = 50;

                // Particle data
                const particleCount = 2000;
                const particles = [];
                const sphereRadius = 15;
                const geometry = new THREE.BufferGeometry();
                const positions = new Float32Array(particleCount * 3);
                const colors = new Float32Array(particleCount * 3);

                // Initialize particles in sphere
                for (let i = 0; i < particleCount; i++) {
                    const theta = Math.random() * Math.PI * 2;
                    const phi = Math.acos(Math.random() * 2 - 1);
                    const r = sphereRadius + (Math.random() - 0.5) * 2;

                    const x = r * Math.sin(phi) * Math.cos(theta);
                    const y = r * Math.sin(phi) * Math.sin(theta);
                    const z = r * Math.cos(phi);

                    positions[i * 3] = x;
                    positions[i * 3 + 1] = y;
                    positions[i * 3 + 2] = z;

                    colors[i * 3] = 0.3;
                    colors[i * 3 + 1] = 0.66;
                    colors[i * 3 + 2] = 0.91;

                    particles.push({
                        x, y, z,
                        vx: (Math.random() - 0.5) * 0.02,
                        vy: (Math.random() - 0.5) * 0.02,
                        vz: (Math.random() - 0.5) * 0.02,
                        baseX: x,
                        baseY: y,
                        baseZ: z
                    });
                }

                geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
                geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                const material = new THREE.PointsMaterial({
                    size: 0.3,
                    vertexColors: true,
                    transparent: true,
                    opacity: 0.8,
                    sizeAttenuation: true
                });

                const points = new THREE.Points(geometry, material);
                scene.add(points);

                // Connection lines setup
                const lineGeometry = new THREE.BufferGeometry();
                const lineMaterial = new THREE.LineBasicMaterial({
                    color: 0x4ca8e8,
                    transparent: true,
                    opacity: 0.2,
                    linewidth: 1
                });
                const lines = new THREE.LineSegments(lineGeometry, lineMaterial);
                scene.add(lines);

                const connectionDistance = 12;

                // Electron dots for thinking state
                const electronGeometry = new THREE.BufferGeometry();
                const electronMaterial = new THREE.PointsMaterial({
                    color: 0x4ca8e8,
                    size: 0.5,
                    transparent: true,
                    opacity: 0.9
                });
                const electrons = new THREE.Points(electronGeometry, electronMaterial);
                scene.add(electrons);

                let electrons_visible = false;
                const electronTrails = [];

                // State management
                let state = 'idle';
                let stateTime = 0;
                const stateTransitionDuration = 0.8;
                let cameraAngle = 0;
                let breathePhase = 0;

                // WebSocket connection
                let ws = null;
                let reconnectAttempts = 0;
                const maxReconnectAttempts = 10;
                const reconnectDelay = 2000;

                function connectWebSocket() {
                    try {
                        ws = new WebSocket('ws://localhost:8741/ws/overlay');

                        ws.onopen = () => {
                            console.log('WebSocket connected');
                            reconnectAttempts = 0;
                        };

                        ws.onmessage = (event) => {
                            const data = JSON.parse(event.data);
                            if (data.state) {
                                setState(data.state);
                            }
                        };

                        ws.onclose = () => {
                            console.log('WebSocket disconnected, attempting reconnect...');
                            if (reconnectAttempts < maxReconnectAttempts) {
                                reconnectAttempts++;
                                setTimeout(connectWebSocket, reconnectDelay);
                            }
                        };

                        ws.onerror = (error) => {
                            console.error('WebSocket error:', error);
                        };
                    } catch (error) {
                        console.error('WebSocket connection failed:', error);
                    }
                }

                connectWebSocket();

                function setState(newState) {
                    if (state !== newState) {
                        state = newState;
                        stateTime = 0;
                        electrons_visible = (newState === 'thinking');
                    }
                }

                function updateParticles() {
                    const positionAttribute = geometry.getAttribute('position');
                    const positions = positionAttribute.array;

                    let compactness = 0.8;
                    let speed = 0.01;
                    let brightness = 0.8;

                    const progress = Math.min(stateTime / stateTransitionDuration, 1);

                    switch (state) {
                        case 'idle':
                            compactness = 0.3 + progress * 0.5;
                            speed = 0.005;
                            brightness = 0.6 + progress * 0.2;
                            break;
                        case 'listening':
                            compactness = 0.7 + progress * 0.2;
                            speed = 0.015;
                            brightness = 0.85 + progress * 0.15;
                            break;
                        case 'thinking':
                            compactness = 0.95 + progress * 0.05;
                            speed = 0.03;
                            brightness = 1;
                            break;
                        case 'speaking':
                            compactness = 0.8 + Math.sin(stateTime * 3) * 0.1;
                            speed = 0.02;
                            brightness = 0.9 + Math.sin(stateTime * 2) * 0.1;
                            break;
                    }

                    for (let i = 0; i < particleCount; i++) {
                        const particle = particles[i];

                        particle.vx += (Math.random() - 0.5) * speed;
                        particle.vy += (Math.random() - 0.5) * speed;
                        particle.vz += (Math.random() - 0.5) * speed;

                        const velocityDamping = 0.95;
                        particle.vx *= velocityDamping;
                        particle.vy *= velocityDamping;
                        particle.vz *= velocityDamping;

                        particle.x += particle.vx;
                        particle.y += particle.vy;
                        particle.z += particle.vz;

                        const targetDist = sphereRadius * compactness;
                        const currentDist = Math.sqrt(particle.x * particle.x + particle.y * particle.y + particle.z * particle.z);
                        const correctionFactor = targetDist / Math.max(currentDist, 0.1);

                        particle.x *= (1 - 0.02) + particle.baseX * 0.02 * correctionFactor;
                        particle.y *= (1 - 0.02) + particle.baseY * 0.02 * correctionFactor;
                        particle.z *= (1 - 0.02) + particle.baseZ * 0.02 * correctionFactor;

                        const boundRadius = sphereRadius * 1.5;
                        const dist = Math.sqrt(particle.x * particle.x + particle.y * particle.y + particle.z * particle.z);
                        if (dist > boundRadius) {
                            const scale = boundRadius / dist;
                            particle.x *= scale;
                            particle.y *= scale;
                            particle.z *= scale;
                        }

                        positions[i * 3] = particle.x;
                        positions[i * 3 + 1] = particle.y;
                        positions[i * 3 + 2] = particle.z;
                    }

                    positionAttribute.needsUpdate = true;

                    // Update colors based on brightness
                    const colorAttribute = geometry.getAttribute('color');
                    const colorArray = colorAttribute.array;
                    for (let i = 0; i < particleCount; i++) {
                        colorArray[i * 3] = 0.3 * brightness;
                        colorArray[i * 3 + 1] = 0.66 * brightness;
                        colorArray[i * 3 + 2] = 0.91 * brightness;
                    }
                    colorAttribute.needsUpdate = true;
                }

                function updateConnections() {
                    const linePositions = [];
                    const positionAttribute = geometry.getAttribute('position');
                    const positions = positionAttribute.array;

                    for (let i = 0; i < particleCount; i++) {
                        for (let j = i + 1; j < particleCount; j++) {
                            const pi = i * 3;
                            const pj = j * 3;

                            const dx = positions[pj] - positions[pi];
                            const dy = positions[pj + 1] - positions[pi + 1];
                            const dz = positions[pj + 2] - positions[pi + 2];

                            const distSq = dx * dx + dy * dy + dz * dz;

                            if (distSq < connectionDistance * connectionDistance) {
                                linePositions.push(positions[pi], positions[pi + 1], positions[pi + 2]);
                                linePositions.push(positions[pj], positions[pj + 1], positions[pj + 2]);
                            }
                        }
                    }

                    lineGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(linePositions), 3));
                }

                function updateElectrons() {
                    if (!electrons_visible || electronTrails.length === 0) {
                        electronGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(0), 3));
                        return;
                    }

                    const electronPositions = [];
                    for (const trail of electronTrails) {
                        trail.progress += 0.02;
                        if (trail.progress > 1) {
                            trail.progress = 0;
                        }

                        const startPos = trail.start;
                        const endPos = trail.end;

                        const x = startPos.x + (endPos.x - startPos.x) * trail.progress;
                        const y = startPos.y + (endPos.y - startPos.y) * trail.progress;
                        const z = startPos.z + (endPos.z - startPos.z) * trail.progress;

                        electronPositions.push(x, y, z);
                    }

                    electronGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(electronPositions), 3));
                }

                function createElectronTrails() {
                    if (!electrons_visible) return;

                    electronTrails.length = 0;
                    const positionAttribute = geometry.getAttribute('position');
                    const positions = positionAttribute.array;

                    for (let i = 0; i < Math.min(particleCount, 200); i++) {
                        for (let j = i + 1; j < Math.min(particleCount, 300); j++) {
                            const pi = i * 3;
                            const pj = j * 3;

                            const dx = positions[pj] - positions[pi];
                            const dy = positions[pj + 1] - positions[pi + 1];
                            const dz = positions[pj + 2] - positions[pi + 2];

                            const distSq = dx * dx + dy * dy + dz * dz;

                            if (distSq < (connectionDistance * 0.8) * (connectionDistance * 0.8)) {
                                electronTrails.push({
                                    start: {
                                        x: positions[pi],
                                        y: positions[pi + 1],
                                        z: positions[pi + 2]
                                    },
                                    end: {
                                        x: positions[pj],
                                        y: positions[pj + 1],
                                        z: positions[pj + 2]
                                    },
                                    progress: Math.random()
                                });

                                if (electronTrails.length > 100) break;
                            }
                        }
                        if (electronTrails.length > 100) break;
                    }
                }

                function animate() {
                    requestAnimationFrame(animate);

                    stateTime += 1 / 60;

                    // Camera drift
                    cameraAngle += 0.0005;
                    const driftRadius = 3;
                    camera.position.x = Math.sin(cameraAngle) * driftRadius;
                    camera.position.y = Math.cos(cameraAngle * 0.7) * driftRadius * 0.5;

                    // Z-axis breathing
                    breathePhase += 0.01;
                    camera.position.z = 50 + Math.sin(breathePhase) * 2;

                    updateParticles();
                    updateConnections();

                    if (electrons_visible) {
                        if (stateTime % 5 < 0.1) {
                            createElectronTrails();
                        }
                        updateElectrons();
                    }

                    camera.lookAt(0, 0, 0);
                    renderer.render(scene, camera);
                }

                animate();

                window.addEventListener('resize', () => {
                    camera.aspect = window.innerWidth / window.innerHeight;
                    camera.updateProjectionMatrix();
                    renderer.setSize(window.innerWidth, window.innerHeight);
                });
            </script>
        </body>
        </html>
        """

        webView.loadHTMLString(htmlContent, baseURL: nil)
        window.makeKeyAndOrderFront(nil)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool {
        return true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
