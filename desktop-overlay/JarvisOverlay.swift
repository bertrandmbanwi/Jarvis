import Cocoa
import WebKit
import CoreGraphics
import Carbon

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var webView: WKWebView?
    var hotKeyRef: EventHotKeyRef?
    var hotKeyHandler: EventHandlerRef?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let screenFrame = screen.frame

        // Transparent floating surface for the orb, status, and response text.
        let windowSize = CGSize(width: 360, height: 400)
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
                    padding: 18px 10px 8px;
                    position: relative;
                }

                #panel {
                    display: none;
                }

                /* Status indicator row */
                #status-row {
                    position: relative;
                    z-index: 10;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin-top: 2px;
                    margin-bottom: 0;
                    text-shadow: 0 0 10px rgba(0, 0, 0, 0.78);
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
                    text-shadow: 0 0 12px rgba(0, 0, 0, 0.85);
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
                    border-radius: 50%;
                    overflow: hidden;
                    -webkit-mask-image: radial-gradient(circle, #000 0%, #000 66%, rgba(0, 0, 0, 0.72) 76%, transparent 88%);
                    mask-image: radial-gradient(circle, #000 0%, #000 66%, rgba(0, 0, 0, 0.72) 76%, transparent 88%);
                    filter: brightness(1.1) saturate(1.08) drop-shadow(0 0 18px rgba(0, 212, 255, 0.22));
                }
                #orb-container::before {
                    content: '';
                    position: absolute;
                    inset: 6%;
                    border-radius: 50%;
                    background:
                        radial-gradient(circle,
                            rgba(1, 7, 15, 0.56) 0%,
                            rgba(1, 10, 20, 0.36) 42%,
                            rgba(1, 10, 20, 0.14) 64%,
                            transparent 82%);
                    filter: blur(8px);
                    pointer-events: none;
                }
                #orb-container canvas {
                    display: block;
                    width: 100%;
                    height: 100%;
                    position: relative;
                    z-index: 1;
                }

                /* Text display area below orb */
                #text-area {
                    position: relative;
                    z-index: 10;
                    width: 320px;
                    padding: 0 18px;
                    text-align: center;
                    max-height: 100px;
                    overflow: hidden;
                    text-shadow:
                        0 0 12px rgba(0, 0, 0, 0.95),
                        0 1px 2px rgba(0, 0, 0, 0.95);
                }

                #user-text {
                    font-size: 10px;
                    color: rgba(0, 212, 255, 0.58);
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
                    color: rgba(255, 255, 255, 0.68);
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
            <script type="module">
                import * as THREE from './three.module.min.js';
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
                const particleCount = 2200;
                const particles = [];
                const sphereRadius = 10.9;
                const geometry = new THREE.BufferGeometry();
                const positions = new Float32Array(particleCount * 3);
                const colors = new Float32Array(particleCount * 3);
                const sizes = new Float32Array(particleCount);

                // Distribute particles in 3 overlapping shells for a cohesive orb
                const shellRadii = [sphereRadius * 0.52, sphereRadius * 0.74, sphereRadius * 0.90];
                const shellCounts = [550, 1100, 550];
                let idx = 0;

                for (let shell = 0; shell < 3; shell++) {
                    const r = shellRadii[shell];
                    const count = shellCounts[shell];
                    for (let i = 0; i < count; i++) {
                        const theta = Math.random() * Math.PI * 2;
                        const jitter = (Math.random() - 0.5) * 2.0;
                        const pr = r + jitter;
                        const screenR = Math.sqrt(Math.random()) * pr;

                        const x = screenR * Math.cos(theta);
                        const y = screenR * Math.sin(theta);
                        const zLimit = Math.sqrt(Math.max(0, pr * pr - screenR * screenR));
                        const z = (Math.random() * 2 - 1) * zLimit;

                        positions[idx * 3] = x;
                        positions[idx * 3 + 1] = y;
                        positions[idx * 3 + 2] = z;

                        // Cyan color: rgb(0, 212, 255) = (0, 0.832, 1.0)
                        colors[idx * 3] = 0.0;
                        colors[idx * 3 + 1] = 0.832;
                        colors[idx * 3 + 2] = 1.0;

                        sizes[idx] = shell === 0 ? 0.44 : shell === 1 ? 0.31 : 0.22;

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
                    size: 0.74,
                    map: dotTexture,
                    vertexColors: true,
                    transparent: true,
                    opacity: 0.86,
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
                    opacity: 0.38,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false
                });
                const glowSprite = new THREE.Sprite(glowMaterial);
                glowSprite.scale.set(20, 20, 1);
                scene.add(glowSprite);

                function createGlowTexture() {
                    const canvas = document.createElement('canvas');
                    canvas.width = 128;
                    canvas.height = 128;
                    const ctx = canvas.getContext('2d');
                    const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
                    gradient.addColorStop(0, 'rgba(255,255,255,0.72)');
                    gradient.addColorStop(0.15, 'rgba(0,212,255,0.42)');
                    gradient.addColorStop(0.4, 'rgba(0,140,200,0.12)');
                    gradient.addColorStop(0.7, 'rgba(0,80,120,0.04)');
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
                let voiceSpeaking = false;
                let currentAudioAmp = 0;
                let amplitudeEnvelope = [];
                let amplitudeDuration = 0;
                let amplitudeStartMs = 0;

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
                                if (data.activationAccepted === false) setState('idle');
                                if (data.state) setState(data.state);
                                if (data.text !== undefined) setResponseText(data.text);
                                if (data.userText !== undefined) setUserText(data.userText);
                                if (data.voiceSpeaking !== undefined || data.voice_speaking !== undefined) {
                                    setVoiceSpeaking(Boolean(data.voiceSpeaking ?? data.voice_speaking));
                                }
                                const envelope = data.amplitudeEnvelope || data.amplitude_envelope;
                                const duration = data.audioDuration || data.audio_duration;
                                if (Array.isArray(envelope) && duration > 0) {
                                    startAmplitudeEnvelope(envelope, duration);
                                }
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

                function sendOverlayCommand(command) {
                    if (!ws || ws.readyState !== WebSocket.OPEN) {
                        return false;
                    }
                    ws.send(JSON.stringify({ command }));
                    return true;
                }

                window.jarvisActivateVoice = function() {
                    setState('listening');
                    setUserText('');
                    setResponseText('');
                    sendOverlayCommand('activate_voice');
                };

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
                            targetBrightness = 0.76;
                            showConnections = false;
                            targetColor = cyanColor;
                            targetGlowIntensity = 0.42;
                            break;
                        case 'listening':
                            targetCompactness = 0.92;
                            targetSpeed = 0.015;
                            targetBrightness = 0.92;
                            showConnections = false;
                            targetColor = cyanColor;
                            targetGlowIntensity = 0.54;
                            break;
                        case 'thinking':
                            targetCompactness = 1.0;
                            targetSpeed = 0.035;
                            targetBrightness = 1.0;
                            showConnections = true;
                            targetColor = whiteColor;
                            targetGlowIntensity = 0.68;
                            break;
                        case 'speaking':
                            targetCompactness = 0.84;
                            targetSpeed = 0.028;
                            targetBrightness = 0.98;
                            showConnections = false;
                            targetColor = goldColor;
                            targetGlowIntensity = 0.62;
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

                function setVoiceSpeaking(speaking) {
                    voiceSpeaking = speaking;
                    if (speaking) {
                        if (state !== 'speaking') setState('speaking');
                        return;
                    }

                    amplitudeEnvelope = [];
                    amplitudeDuration = 0;
                    currentAudioAmp = 0;
                    setResponseText('');
                    setUserText('');
                    if (state === 'speaking') setState('idle');
                }

                function startAmplitudeEnvelope(envelope, duration) {
                    amplitudeEnvelope = envelope;
                    amplitudeDuration = duration;
                    amplitudeStartMs = performance.now();
                    currentAudioAmp = 0;
                    setVoiceSpeaking(true);
                }

                function nextAudioAmplitude() {
                    if (amplitudeEnvelope.length > 0 && amplitudeDuration > 0) {
                        const elapsed = (performance.now() - amplitudeStartMs) / 1000;
                        if (elapsed < amplitudeDuration) {
                            const progress = elapsed / amplitudeDuration;
                            const envelopeIndex = Math.min(
                                Math.floor(progress * amplitudeEnvelope.length),
                                amplitudeEnvelope.length - 1
                            );
                            const targetAmp = Number(amplitudeEnvelope[envelopeIndex]) || 0;
                            currentAudioAmp += (targetAmp - currentAudioAmp) * 0.35;
                            return currentAudioAmp;
                        }

                        amplitudeEnvelope = [];
                        amplitudeDuration = 0;
                    }

                    if (voiceSpeaking || state === 'speaking') {
                        // Fallback for TTS backends that cannot provide an envelope.
                        const syllable = Math.pow((Math.sin(stateTime * 10.0) + 1) * 0.5, 2.2);
                        const carrier = Math.pow((Math.sin(stateTime * 17.0 + 0.8) + 1) * 0.5, 1.8);
                        const targetAmp = 0.18 + syllable * 0.34 + carrier * 0.18;
                        currentAudioAmp += (targetAmp - currentAudioAmp) * 0.22;
                        return currentAudioAmp;
                    }

                    currentAudioAmp *= 0.86;
                    return currentAudioAmp;
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

                    const audioAmp = nextAudioAmplitude();
                    const reactiveSpeed = currentSpeed * (1 + audioAmp * 3.4);
                    const reactiveBrightness = Math.min(1.18, currentBrightness + audioAmp * 0.28);

                    // Breathing effect
                    const breathe = Math.sin(breathePhase) * (0.035 + audioAmp * 0.12);

                    for (let i = 0; i < particleCount; i++) {
                        const p = particles[i];

                        // Sinusoidal noise-based motion (like ethanplusai's approach)
                        const t = stateTime * p.orbitSpeed * reactiveSpeed * 8;
                        const noiseScale = 0.08 + audioAmp * 0.16;
                        const noiseX = Math.sin(t + p.baseX * 0.5) * noiseScale;
                        const noiseY = Math.cos(t * 0.7 + p.baseY * 0.5) * noiseScale;
                        const noiseZ = Math.sin(t * 0.9 + p.baseZ * 0.5) * noiseScale;

                        // Apply noise as velocity perturbation
                        p.vx += noiseX * reactiveSpeed * 2;
                        p.vy += noiseY * reactiveSpeed * 2;
                        p.vz += noiseZ * reactiveSpeed * 2;

                        // Damping
                        p.vx *= 0.92;
                        p.vy *= 0.92;
                        p.vz *= 0.92;

                        p.x += p.vx;
                        p.y += p.vy;
                        p.z += p.vz;

                        // Centripetal pull: scale current position toward target shell radius
                        const shellReaction = p.shell === 0 ? 0.07 : p.shell === 1 ? 0.12 : 0.16;
                        const audioExpansion = 1 + audioAmp * shellReaction;
                        const targetR = shellRadii[p.shell] * currentCompactness * (1 + breathe) * audioExpansion;
                        const dist = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
                        if (dist > 0.01) {
                            const pullStrength = 0.04;
                            const scaleFactor = 1.0 + (targetR / dist - 1.0) * pullStrength;
                            p.x *= scaleFactor;
                            p.y *= scaleFactor;
                            p.z *= scaleFactor;
                        }

                        const screenR = Math.sqrt(p.x * p.x + p.y * p.y);
                        const silhouetteLimit = shellRadii[2] * currentCompactness * (1.04 + audioAmp * 0.08);
                        if (screenR > silhouetteLimit) {
                            const screenScale = silhouetteLimit / screenR;
                            p.x *= screenScale;
                            p.y *= screenScale;
                        }
                        const radialNorm = Math.min(screenR / silhouetteLimit, 1);
                        const edgeFalloff = 1 - Math.pow(radialNorm, 2.8) * 0.52;
                        const shellFalloff = p.shell === 2 ? 0.78 : p.shell === 1 ? 0.92 : 1.0;
                        const particleBrightness = reactiveBrightness * edgeFalloff * shellFalloff;

                        pos[i * 3] = p.x;
                        pos[i * 3 + 1] = p.y;
                        pos[i * 3 + 2] = p.z;

                        // Color with brightness
                        col[i * 3]     = currentColor[0] * particleBrightness;
                        col[i * 3 + 1] = currentColor[1] * particleBrightness;
                        col[i * 3 + 2] = currentColor[2] * particleBrightness;
                    }

                    posAttr.needsUpdate = true;
                    colAttr.needsUpdate = true;

                    // Update glow
                    glowMaterial.opacity = Math.min(0.78, currentGlowIntensity + audioAmp * 0.24);
                    const glowHue = new THREE.Color(currentColor[0], currentColor[1], currentColor[2]);
                    glowMaterial.color = glowHue;
                    const glowScale = 19 + Math.sin(breathePhase) * 1.4 + audioAmp * 4.8;
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
                    breathePhase += 0.008 + currentAudioAmp * 0.022;
                    camera.position.z = 30 + Math.sin(breathePhase) * (1.0 + currentAudioAmp * 1.8);

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

        webView.loadHTMLString(htmlContent, baseURL: Bundle.main.resourceURL)
        window.makeKeyAndOrderFront(nil)
        registerGlobalHotKey()
    }

    func registerGlobalHotKey() {
        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )

        let callback: EventHandlerUPP = { _, _, userData in
            guard let userData = userData else { return noErr }
            let delegate = Unmanaged<AppDelegate>.fromOpaque(userData).takeUnretainedValue()
            DispatchQueue.main.async {
                delegate.handleHotKey()
            }
            return noErr
        }

        let handlerStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            callback,
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            &hotKeyHandler
        )

        guard handlerStatus == noErr else {
            NSLog("JARVIS overlay hotkey handler registration failed: \(handlerStatus)")
            return
        }

        let hotKeyID = EventHotKeyID(signature: fourCharCode("JRVS"), id: 1)
        let hotKeyStatus = RegisterEventHotKey(
            UInt32(kVK_ANSI_J),
            UInt32(controlKey | optionKey),
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )

        if hotKeyStatus != noErr {
            NSLog("JARVIS overlay hotkey registration failed: \(hotKeyStatus)")
        }
    }

    func unregisterGlobalHotKey() {
        if let hotKeyRef = hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        if let hotKeyHandler = hotKeyHandler {
            RemoveEventHandler(hotKeyHandler)
            self.hotKeyHandler = nil
        }
    }

    func handleHotKey() {
        webView?.evaluateJavaScript(
            "window.jarvisActivateVoice && window.jarvisActivateVoice();",
            completionHandler: nil
        )
    }

    func applicationWillTerminate(_ notification: Notification) {
        unregisterGlobalHotKey()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool {
        return true
    }
}

func fourCharCode(_ string: String) -> OSType {
    var result: UInt32 = 0
    for scalar in string.unicodeScalars.prefix(4) {
        result = (result << 8) + UInt32(scalar.value)
    }
    return OSType(result)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
