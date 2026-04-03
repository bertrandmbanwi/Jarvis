import Cocoa
import WebKit
import CoreGraphics

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var webView: WKWebView?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let screenFrame = screen.frame

        // Larger window to accommodate status text and response display
        let windowSize = CGSize(width: 380, height: 440)
        let padding: CGFloat = 50
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
        let floatingLevel = Int(CGWindowLevelForKey(.floatingWindow))
        window.level = NSWindow.Level(rawValue: floatingLevel)
        window.ignoresMouseEvents = true
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]

        let webViewConfig = WKWebViewConfiguration()

        webView = WKWebView(frame: window.contentView?.bounds ?? .zero, configuration: webViewConfig)
        guard let webView = webView else { return }

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
                *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
                body, html {
                    width: 100%;
                    height: 100%;
                    background: transparent;
                    overflow: hidden;
                    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif;
                    -webkit-font-smoothing: antialiased;
                }

                #container {
                    width: 100%;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: flex-start;
                    padding: 16px;
                    position: relative;
                }

                /* Dark panel behind everything; no backdrop-filter (WKWebView cannot blur the macOS desktop) */
                #panel {
                    position: absolute;
                    inset: 8px;
                    background: rgba(2, 6, 14, 0.92);
                    border: 1px solid rgba(0, 212, 255, 0.08);
                    border-radius: 20px;
                    box-shadow: 0 0 40px rgba(0, 0, 0, 0.5), inset 0 0 60px rgba(0, 20, 40, 0.3);
                    pointer-events: none;
                }

                /* Status indicator row */
                #status-row {
                    position: relative;
                    z-index: 10;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin-top: 8px;
                    margin-bottom: 4px;
                }

                #status-dot {
                    width: 6px;
                    height: 6px;
                    border-radius: 50%;
                    background: rgba(0, 212, 255, 0.3);
                    transition: background 0.5s ease, box-shadow 0.5s ease;
                }
                #status-dot.listening {
                    background: rgba(0, 212, 255, 0.7);
                    box-shadow: 0 0 8px rgba(0, 212, 255, 0.4);
                    animation: dotPulse 1.2s ease-in-out infinite;
                }
                #status-dot.thinking {
                    background: rgba(255, 225, 140, 0.6);
                    box-shadow: 0 0 8px rgba(255, 225, 140, 0.3);
                    animation: dotPulse 0.8s ease-in-out infinite;
                }
                #status-dot.speaking {
                    background: rgba(255, 225, 140, 0.7);
                    box-shadow: 0 0 10px rgba(255, 225, 140, 0.4);
                }

                @keyframes dotPulse {
                    0%, 100% { opacity: 0.5; transform: scale(1); }
                    50% { opacity: 1; transform: scale(1.3); }
                }

                #status-label {
                    font-size: 9px;
                    font-weight: 500;
                    letter-spacing: 0.2em;
                    text-transform: uppercase;
                    color: rgba(0, 212, 255, 0.35);
                    transition: color 0.5s ease;
                }
                #status-label.listening { color: rgba(0, 212, 255, 0.65); }
                #status-label.thinking  { color: rgba(255, 225, 140, 0.55); }
                #status-label.speaking  { color: rgba(255, 225, 140, 0.65); }

                /* Canvas container for the orb */
                #orb-container {
                    position: relative;
                    z-index: 5;
                    width: 260px;
                    height: 260px;
                    flex-shrink: 0;
                }
                #orb-container canvas {
                    display: block;
                    width: 100%;
                    height: 100%;
                }

                /* Text display area below orb */
                #text-area {
                    position: relative;
                    z-index: 10;
                    width: 100%;
                    padding: 0 20px;
                    text-align: center;
                    max-height: 110px;
                    overflow: hidden;
                }

                #user-text {
                    font-size: 10px;
                    color: rgba(0, 212, 255, 0.35);
                    font-style: italic;
                    margin-bottom: 6px;
                    line-height: 1.4;
                    opacity: 0;
                    transform: translateY(4px);
                    transition: opacity 0.6s ease, transform 0.6s ease;
                    max-height: 28px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                #user-text.visible {
                    opacity: 1;
                    transform: translateY(0);
                }

                #response-text {
                    font-size: 11px;
                    color: rgba(255, 255, 255, 0.50);
                    line-height: 1.5;
                    opacity: 0;
                    transform: translateY(6px);
                    transition: opacity 0.8s ease, transform 0.8s ease;
                    display: -webkit-box;
                    -webkit-line-clamp: 4;
                    -webkit-box-orient: vertical;
                    overflow: hidden;
                }
                #response-text.visible {
                    opacity: 1;
                    transform: translateY(0);
                }
            </style>
        </head>
        <body>
            <div id="container">
                <div id="panel"></div>
                <div id="status-row">
                    <div id="status-dot"></div>
                    <div id="status-label">STANDING BY</div>
                </div>
                <div id="orb-container"></div>
                <div id="text-area">
                    <div id="user-text"></div>
                    <div id="response-text"></div>
                </div>
            </div>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
            <script>
                // --- DOM refs ---
                const statusDot = document.getElementById('status-dot');
                const statusLabel = document.getElementById('status-label');
                const userTextEl = document.getElementById('user-text');
                const responseTextEl = document.getElementById('response-text');
                const orbContainer = document.getElementById('orb-container');

                const stateLabels = {
                    idle: 'STANDING BY',
                    listening: 'LISTENING',
                    thinking: 'PROCESSING',
                    speaking: 'SPEAKING'
                };

                // --- Three.js scene ---
                const scene = new THREE.Scene();
                const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
                const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
                renderer.setSize(260, 260);
                renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
                renderer.setClearColor(0x000000, 0);
                orbContainer.appendChild(renderer.domElement);

                camera.position.z = 30;

                // --- Particle system ---
                const particleCount = 2400;
                const particles = [];
                const sphereRadius = 12;
                const geometry = new THREE.BufferGeometry();
                const positions = new Float32Array(particleCount * 3);
                const colors = new Float32Array(particleCount * 3);
                const sizes = new Float32Array(particleCount);

                // Distribute particles in 3 overlapping shells for a cohesive orb
                const shellRadii = [sphereRadius * 0.55, sphereRadius * 0.78, sphereRadius * 0.95];
                const shellCounts = [600, 1200, 600];
                let idx = 0;

                for (let shell = 0; shell < 3; shell++) {
                    const r = shellRadii[shell];
                    const count = shellCounts[shell];
                    for (let i = 0; i < count; i++) {
                        const theta = Math.random() * Math.PI * 2;
                        const phi = Math.acos(Math.random() * 2 - 1);
                        const jitter = (Math.random() - 0.5) * 3.0;
                        const pr = r + jitter;

                        const x = pr * Math.sin(phi) * Math.cos(theta);
                        const y = pr * Math.sin(phi) * Math.sin(theta);
                        const z = pr * Math.cos(phi);

                        positions[idx * 3] = x;
                        positions[idx * 3 + 1] = y;
                        positions[idx * 3 + 2] = z;

                        // Cyan color: rgb(0, 212, 255) = (0, 0.832, 1.0)
                        colors[idx * 3] = 0.0;
                        colors[idx * 3 + 1] = 0.832;
                        colors[idx * 3 + 2] = 1.0;

                        sizes[idx] = shell === 0 ? 0.5 : shell === 1 ? 0.35 : 0.25;

                        particles.push({
                            x, y, z,
                            vx: (Math.random() - 0.5) * 0.015,
                            vy: (Math.random() - 0.5) * 0.015,
                            vz: (Math.random() - 0.5) * 0.015,
                            baseX: x, baseY: y, baseZ: z,
                            shell: shell,
                            orbitSpeed: (Math.random() * 0.3 + 0.1) * (shell === 0 ? 0.6 : shell === 1 ? 1.0 : 1.4),
                            orbitAxis: new THREE.Vector3(
                                Math.random() - 0.5,
                                Math.random() - 0.5,
                                Math.random() - 0.5
                            ).normalize()
                        });
                        idx++;
                    }
                }

                geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
                geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                // Create a circular soft-dot texture for particles
                const dotTexture = createDotTexture();

                const material = new THREE.PointsMaterial({
                    size: 0.8,
                    map: dotTexture,
                    vertexColors: true,
                    transparent: true,
                    opacity: 0.9,
                    sizeAttenuation: true,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false
                });

                const points = new THREE.Points(geometry, material);
                scene.add(points);

                function createDotTexture() {
                    const size = 64;
                    const canvas = document.createElement('canvas');
                    canvas.width = size;
                    canvas.height = size;
                    const ctx = canvas.getContext('2d');
                    const half = size / 2;
                    const gradient = ctx.createRadialGradient(half, half, 0, half, half, half);
                    gradient.addColorStop(0, 'rgba(255,255,255,1.0)');
                    gradient.addColorStop(0.15, 'rgba(255,255,255,0.8)');
                    gradient.addColorStop(0.4, 'rgba(255,255,255,0.3)');
                    gradient.addColorStop(0.7, 'rgba(255,255,255,0.05)');
                    gradient.addColorStop(1, 'rgba(255,255,255,0)');
                    ctx.fillStyle = gradient;
                    ctx.fillRect(0, 0, size, size);
                    return new THREE.CanvasTexture(canvas);
                }

                // Core glow (sprite)
                const glowTexture = createGlowTexture();
                const glowMaterial = new THREE.SpriteMaterial({
                    map: glowTexture,
                    color: 0x00d4ff,
                    transparent: true,
                    opacity: 0.45,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false
                });
                const glowSprite = new THREE.Sprite(glowMaterial);
                glowSprite.scale.set(24, 24, 1);
                scene.add(glowSprite);

                function createGlowTexture() {
                    const canvas = document.createElement('canvas');
                    canvas.width = 128;
                    canvas.height = 128;
                    const ctx = canvas.getContext('2d');
                    const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
                    gradient.addColorStop(0, 'rgba(255,255,255,0.9)');
                    gradient.addColorStop(0.15, 'rgba(0,212,255,0.5)');
                    gradient.addColorStop(0.4, 'rgba(0,140,200,0.15)');
                    gradient.addColorStop(0.7, 'rgba(0,80,120,0.05)');
                    gradient.addColorStop(1, 'rgba(0,0,0,0)');
                    ctx.fillStyle = gradient;
                    ctx.fillRect(0, 0, 128, 128);
                    const texture = new THREE.CanvasTexture(canvas);
                    return texture;
                }

                // Connection lines (only visible during thinking state)
                const lineGeometry = new THREE.BufferGeometry();
                // Initialize with empty positions so no stale lines render
                lineGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(0), 3));
                const lineMaterial = new THREE.LineBasicMaterial({
                    color: 0x00d4ff,
                    transparent: true,
                    opacity: 0.08,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false
                });
                const lines = new THREE.LineSegments(lineGeometry, lineMaterial);
                scene.add(lines);

                // --- State management ---
                let state = 'idle';
                let stateTime = 0;
                let cameraAngle = 0;
                let breathePhase = 0;
                let targetCompactness = 0.8;
                let currentCompactness = 0.8;
                let targetSpeed = 0.005;
                let currentSpeed = 0.005;
                let targetBrightness = 0.6;
                let currentBrightness = 0.6;
                let showConnections = false;
                let targetGlowIntensity = 0.45;
                let currentGlowIntensity = 0.45;

                // Color targets for state transitions
                const cyanColor = [0.0, 0.832, 1.0];
                const goldColor = [1.0, 0.88, 0.55];
                const whiteColor = [0.9, 0.95, 1.0];
                let targetColor = cyanColor;
                let currentColor = [...cyanColor];

                // --- WebSocket ---
                let ws = null;
                let reconnectAttempts = 0;
                const maxReconnectAttempts = 50;
                const reconnectDelay = 3000;

                function connectWebSocket() {
                    try {
                        ws = new WebSocket('ws://localhost:8741/ws/overlay');

                        ws.onopen = () => {
                            console.log('Overlay WS connected');
                            reconnectAttempts = 0;
                        };

                        ws.onmessage = (event) => {
                            try {
                                const data = JSON.parse(event.data);
                                if (data.state) setState(data.state);
                                if (data.text !== undefined) setResponseText(data.text);
                                if (data.userText !== undefined) setUserText(data.userText);
                            } catch (e) {
                                console.error('Parse error:', e);
                            }
                        };

                        ws.onclose = () => {
                            if (reconnectAttempts < maxReconnectAttempts) {
                                reconnectAttempts++;
                                setTimeout(connectWebSocket, reconnectDelay);
                            }
                        };

                        ws.onerror = (error) => {
                            console.error('WS error:', error);
                        };
                    } catch (error) {
                        console.error('WS connection failed:', error);
                        setTimeout(connectWebSocket, reconnectDelay);
                    }
                }

                connectWebSocket();

                function setState(newState) {
                    if (state === newState) return;
                    state = newState;
                    stateTime = 0;

                    // Update DOM
                    statusDot.className = newState;
                    statusLabel.className = newState;
                    statusLabel.textContent = stateLabels[newState] || 'STANDING BY';

                    // Update visual targets
                    switch (newState) {
                        case 'idle':
                            targetCompactness = 0.85;
                            targetSpeed = 0.005;
                            targetBrightness = 0.75;
                            showConnections = false;
                            targetColor = cyanColor;
                            targetGlowIntensity = 0.45;
                            break;
                        case 'listening':
                            targetCompactness = 0.92;
                            targetSpeed = 0.015;
                            targetBrightness = 0.95;
                            showConnections = false;
                            targetColor = cyanColor;
                            targetGlowIntensity = 0.55;
                            break;
                        case 'thinking':
                            targetCompactness = 1.0;
                            targetSpeed = 0.035;
                            targetBrightness = 1.0;
                            showConnections = true;
                            targetColor = whiteColor;
                            targetGlowIntensity = 0.7;
                            break;
                        case 'speaking':
                            targetCompactness = 0.88;
                            targetSpeed = 0.018;
                            targetBrightness = 0.95;
                            showConnections = false;
                            targetColor = goldColor;
                            targetGlowIntensity = 0.6;
                            break;
                    }
                }

                function setResponseText(text) {
                    if (!text) {
                        responseTextEl.classList.remove('visible');
                        return;
                    }
                    const display = text.length > 180 ? text.slice(0, 180) + '...' : text;
                    responseTextEl.textContent = display;
                    responseTextEl.classList.add('visible');
                }

                function setUserText(text) {
                    if (!text) {
                        userTextEl.classList.remove('visible');
                        return;
                    }
                    userTextEl.textContent = '"' + text + '"';
                    userTextEl.classList.add('visible');
                }

                // --- Animation ---
                const connectionDistance = 8;
                let frameCount = 0;

                function updateParticles() {
                    const posAttr = geometry.getAttribute('position');
                    const pos = posAttr.array;
                    const colAttr = geometry.getAttribute('color');
                    const col = colAttr.array;

                    // Smooth interpolation
                    const lerp = 0.04;
                    currentCompactness += (targetCompactness - currentCompactness) * lerp;
                    currentSpeed += (targetSpeed - currentSpeed) * lerp;
                    currentBrightness += (targetBrightness - currentBrightness) * lerp;
                    currentGlowIntensity += (targetGlowIntensity - currentGlowIntensity) * lerp;
                    currentColor[0] += (targetColor[0] - currentColor[0]) * lerp;
                    currentColor[1] += (targetColor[1] - currentColor[1]) * lerp;
                    currentColor[2] += (targetColor[2] - currentColor[2]) * lerp;

                    // Breathing effect
                    const breathe = Math.sin(breathePhase) * 0.03;

                    for (let i = 0; i < particleCount; i++) {
                        const p = particles[i];

                        // Sinusoidal noise-based motion (like ethanplusai's approach)
                        const t = stateTime * p.orbitSpeed * currentSpeed * 8;
                        const noiseX = Math.sin(t + p.baseX * 0.5) * 0.08;
                        const noiseY = Math.cos(t * 0.7 + p.baseY * 0.5) * 0.08;
                        const noiseZ = Math.sin(t * 0.9 + p.baseZ * 0.5) * 0.08;

                        // Apply noise as velocity perturbation
                        p.vx += noiseX * currentSpeed * 2;
                        p.vy += noiseY * currentSpeed * 2;
                        p.vz += noiseZ * currentSpeed * 2;

                        // Damping
                        p.vx *= 0.92;
                        p.vy *= 0.92;
                        p.vz *= 0.92;

                        p.x += p.vx;
                        p.y += p.vy;
                        p.z += p.vz;

                        // Centripetal pull: scale current position toward target shell radius
                        const targetR = shellRadii[p.shell] * currentCompactness * (1 + breathe);
                        const dist = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
                        if (dist > 0.01) {
                            const pullStrength = 0.04;
                            const scaleFactor = 1.0 + (targetR / dist - 1.0) * pullStrength;
                            p.x *= scaleFactor;
                            p.y *= scaleFactor;
                            p.z *= scaleFactor;
                        }

                        pos[i * 3] = p.x;
                        pos[i * 3 + 1] = p.y;
                        pos[i * 3 + 2] = p.z;

                        // Color with brightness
                        col[i * 3]     = currentColor[0] * currentBrightness;
                        col[i * 3 + 1] = currentColor[1] * currentBrightness;
                        col[i * 3 + 2] = currentColor[2] * currentBrightness;
                    }

                    posAttr.needsUpdate = true;
                    colAttr.needsUpdate = true;

                    // Update glow
                    glowMaterial.opacity = currentGlowIntensity;
                    const glowHue = new THREE.Color(currentColor[0], currentColor[1], currentColor[2]);
                    glowMaterial.color = glowHue;
                    const glowScale = 22 + Math.sin(breathePhase) * 2;
                    glowSprite.scale.set(glowScale, glowScale, 1);
                }

                function updateConnections() {
                    if (!showConnections) {
                        if (lineGeometry.getAttribute('position')) {
                            lineGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(0), 3));
                        }
                        return;
                    }

                    const linePositions = [];
                    const posAttr = geometry.getAttribute('position');
                    const pos = posAttr.array;

                    // Only check inner shell particles for connections (performance)
                    const checkCount = Math.min(400, particleCount);
                    let lineCount = 0;
                    const maxLines = 120;

                    for (let i = 0; i < checkCount && lineCount < maxLines; i++) {
                        for (let j = i + 1; j < checkCount && lineCount < maxLines; j++) {
                            const pi = i * 3;
                            const pj = j * 3;
                            const dx = pos[pj] - pos[pi];
                            const dy = pos[pj + 1] - pos[pi + 1];
                            const dz = pos[pj + 2] - pos[pi + 2];
                            const distSq = dx * dx + dy * dy + dz * dz;

                            if (distSq < connectionDistance * connectionDistance) {
                                linePositions.push(pos[pi], pos[pi + 1], pos[pi + 2]);
                                linePositions.push(pos[pj], pos[pj + 1], pos[pj + 2]);
                                lineCount++;
                            }
                        }
                    }

                    lineGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(linePositions), 3));
                }

                function animate() {
                    requestAnimationFrame(animate);

                    stateTime += 1 / 60;
                    frameCount++;

                    // Camera drift
                    cameraAngle += 0.0004;
                    const driftR = 2.5;
                    camera.position.x = Math.sin(cameraAngle) * driftR;
                    camera.position.y = Math.cos(cameraAngle * 0.7) * driftR * 0.5;

                    // Breathing
                    breathePhase += 0.008;
                    camera.position.z = 30 + Math.sin(breathePhase) * 1.0;

                    updateParticles();

                    // Update connections every 3rd frame for performance
                    if (frameCount % 3 === 0) {
                        updateConnections();
                    }

                    camera.lookAt(0, 0, 0);
                    renderer.render(scene, camera);
                }

                animate();
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
