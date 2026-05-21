"use client";

const C = {
  cyan: [0.0, 0.832, 1.0],
  cyanBrite: [0.549, 0.882, 1.0],
  cyanDeep: [0.0, 0.549, 0.863],
  cyanPale: [0.314, 0.784, 1.0],
  speakCore: [1.0, 0.92, 0.78],
  speakPart: [0.2, 0.78, 0.92],
  speakGlow: [0.1, 0.62, 0.82],
  white: [1.0, 1.0, 1.0],
  errRed: [1.0, 0.314, 0.157],
  errPale: [1.0, 0.627, 0.549],
  thinkA: [0.35, 0.72, 0.95],
  thinkB: [0.2, 0.58, 0.88],
};

export const ORB_STATES = {
  idle: {
    coreColor: C.cyanBrite,
    particleColor: C.cyan,
    glowColor: C.cyanDeep,
    coreIntensity: 0.72,
    particleAlpha: 0.78,
    orbitalSpeed: 0.04,
    turbulence: 0.012,
    pulseRate: 0.45,
    pulseDepth: 0.18,
    trailStrength: 0.0,
    arcFrequency: 0.0,
    breathBlend: 0.7,
    scaleTarget: 1.0,
    dustAlpha: 0.32,
    ringAlpha: 0.22,
  },
  listening: {
    coreColor: C.cyanBrite,
    particleColor: C.cyanPale,
    glowColor: C.cyanDeep,
    coreIntensity: 0.86,
    particleAlpha: 0.84,
    orbitalSpeed: 0.1,
    turbulence: 0.03,
    pulseRate: 0.8,
    pulseDepth: 0.24,
    trailStrength: 0.06,
    arcFrequency: 0.15,
    breathBlend: 0.3,
    scaleTarget: 0.93,
    dustAlpha: 0.34,
    ringAlpha: 0.24,
  },
  thinking: {
    coreColor: C.white,
    particleColor: C.thinkA,
    glowColor: C.thinkB,
    coreIntensity: 0.96,
    particleAlpha: 0.88,
    orbitalSpeed: 0.28,
    turbulence: 0.06,
    pulseRate: 1.2,
    pulseDepth: 0.3,
    trailStrength: 0.14,
    arcFrequency: 0.5,
    breathBlend: 0.1,
    scaleTarget: 0.94,
    dustAlpha: 0.36,
    ringAlpha: 0.25,
  },
  speaking: {
    coreColor: C.speakCore,
    particleColor: C.speakPart,
    glowColor: C.speakGlow,
    coreIntensity: 0.94,
    particleAlpha: 0.86,
    orbitalSpeed: 0.07,
    turbulence: 0.025,
    pulseRate: 0.55,
    pulseDepth: 0.38,
    trailStrength: 0.1,
    arcFrequency: 0.25,
    breathBlend: 0.85,
    scaleTarget: 1.05,
    dustAlpha: 0.34,
    ringAlpha: 0.24,
  },
  error: {
    coreColor: C.errPale,
    particleColor: C.errRed,
    glowColor: C.errRed,
    coreIntensity: 0.45,
    particleAlpha: 0.75,
    orbitalSpeed: 0.03,
    turbulence: 0.025,
    pulseRate: 0.45,
    pulseDepth: 0.12,
    trailStrength: 0.0,
    arcFrequency: 0.0,
    breathBlend: 0.08,
    scaleTarget: 0.8,
    dustAlpha: 0.12,
    ringAlpha: 0.1,
  },
};

const PARTICLE_COUNT = 2400;
const DUST_COUNT = 180;
const ARC_COUNT = 8;
const ARC_PTS = 40;

const SHELL_COUNTS = [800, 1200, 400];
const SHELL_SPLIT = [800, 2000, 2400];

const VERT_PARTICLES = /* glsl */ `
  attribute float aSize;
  attribute float aBright;
  attribute float aShell;
  attribute float aPhase;
  attribute vec3  aOrbitAxis;

  uniform float uTime;
  uniform float uPulse;
  uniform float uScale;
  uniform float uAudio;
  uniform float uPointScale;

  varying float vAlpha;
  varying float vShell;

  vec3 mod289(vec3 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
  vec4 mod289(vec4 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
  vec4 perm(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
  float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    vec3 i = floor(v + dot(v, vec3(C.y)));
    vec3 x0 = v - i + dot(i, vec3(C.x));
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g, l.zxy);
    vec3 i2 = max(g, l.zxy);
    vec3 x1 = x0 - i1 + C.x;
    vec3 x2 = x0 - i2 + C.y;
    vec3 x3 = x0 - 0.5;
    i = mod289(i);
    vec4 p = perm(perm(perm(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
    + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    vec4 j = p - 49.0 * floor(p * (1.0/49.0));
    vec4 x_ = floor(j * (1.0/7.0));
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 xx = (x_ * 2.0 + 0.5) / 7.0 - 1.0;
    vec4 yy = (y_ * 2.0 + 0.5) / 7.0 - 1.0;
    vec4 h = 1.0 - abs(xx) - abs(yy);
    vec4 b0 = vec4(xx.xy, yy.xy);
    vec4 b1 = vec4(xx.zw, yy.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 g0 = vec3(a0.xy, h.x);
    vec3 g1 = vec3(a0.zw, h.y);
    vec3 g2 = vec3(a1.xy, h.z);
    vec3 g3 = vec3(a1.zw, h.w);
    vec4 norm = 1.79284291400159 - 0.85373472095314 *
      vec4(dot(g0,g0), dot(g1,g1), dot(g2,g2), dot(g3,g3));
    g0 *= norm.x; g1 *= norm.y; g2 *= norm.z; g3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(g0,x0), dot(g1,x1), dot(g2,x2), dot(g3,x3)));
  }

  vec3 rotateAxis(vec3 p, vec3 axis, float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return p * c + cross(axis, p) * s + axis * dot(axis, p) * (1.0 - c);
  }

  void main() {
    float shellSpeedVariation = 0.4 + aShell * 0.6;
    float angle = uTime * shellSpeedVariation + aPhase * 6.2831853;
    vec3 orbited = rotateAxis(position, normalize(aOrbitAxis), angle);

    float n = snoise(orbited * 3.0 + uTime * 0.25);
    vec3 disp = normalize(orbited) * n * 0.06;

    float audioMix = 1.0 + uAudio * (0.35 - aShell * 0.2);
    float pulseMix = 1.0 + uPulse * 0.10;
    vec3 pos = (orbited + disp) * uScale * pulseMix * audioMix;

    vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mvPos;

    float depth = -mvPos.z;
    float baseSize = aSize * (40.0 / max(depth, 0.5));
    gl_PointSize = max(1.2, baseSize * (0.85 + uPulse * 0.15) * audioMix * uPointScale);

    float depthFade = smoothstep(6.0, 2.5, depth);
    vAlpha = aBright * (0.82 + depthFade * 0.18) * (0.85 + uPulse * 0.15);
    vShell = aShell;
  }
`;

const FRAG_PARTICLES = /* glsl */ `
  uniform vec3  uColor;
  uniform vec3  uCoreCol;
  uniform float uAlpha;

  varying float vAlpha;
  varying float vShell;

  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;

    float core = exp(-d * d * 120.0);
    float glow = exp(-d * d * 18.0);
    float edge = max(0.0, 1.0 - d * 2.0);

    vec3 col = mix(uColor, uCoreCol, core * 0.8 + glow * 0.15);
    float alpha = (core * 0.82 + glow * 0.46 + edge * 0.08) * vAlpha * uAlpha;
    gl_FragColor = vec4(col * alpha * 2.6, min(alpha * 0.82, 1.0));
  }
`;

const VERT_DUST = /* glsl */ `
  attribute float aSize;
  attribute float aPhase;
  uniform float uTime;
  uniform float uScale;
  uniform float uPointScale;
  varying float vFade;

  void main() {
    float t = uTime * 0.03 + aPhase * 6.28;
    float drift = 1.0 + mod(uTime * 0.02 + aPhase, 1.0) * 0.4;
    vec3 pos = position * drift * uScale;
    float c = cos(t); float s = sin(t);
    pos = vec3(pos.x * c - pos.z * s, pos.y, pos.x * s + pos.z * c);

    vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mvPos;
    float depth = -mvPos.z;
    gl_PointSize = aSize * (200.0 / max(depth, 0.5)) * uPointScale;
    vFade = smoothstep(4.5, 2.0, depth);
  }
`;

const FRAG_DUST = /* glsl */ `
  uniform vec3  uColor;
  uniform float uAlpha;
  varying float vFade;

  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float glow = exp(-d * d * 12.0);
    float alpha = glow * vFade * uAlpha * 0.50;
    gl_FragColor = vec4(uColor * alpha * 1.08, alpha);
  }
`;

const VERT_GLOW = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const FRAG_GLOW = /* glsl */ `
  uniform vec3  uCore;
  uniform vec3  uMid;
  uniform vec3  uOuter;
  uniform float uIntensity;
  uniform float uPulse;
  varying vec2  vUv;

  void main() {
    float d = length(vUv - vec2(0.5)) * 2.0;
    float p = 1.0 + uPulse * 0.25;
    float edgeFade = smoothstep(1.12, 0.70, d);

    float L0 = exp(-d * d * 34.0) * 0.95;
    float L1 = exp(-d * d * 10.0) * 0.42 * p;
    float L2 = exp(-d * d * 3.0)  * 0.20 * p;
    float L3 = exp(-d * d * 0.7)  * 0.075;
    float L4 = exp(-d * d * 0.20) * 0.026;

    vec3 col = vec3(1.0) * L0
             + uCore  * L1
             + uMid   * L2
             + uOuter * L3
             + uOuter * L4;

    float alpha = (L0 + L1 + L2 + L3 + L4) * uIntensity * edgeFade;
    gl_FragColor = vec4(col * uIntensity * edgeFade, alpha);
  }
`;

const VERT_ARC = /* glsl */ `
  attribute float aT;
  uniform float uScale;
  varying float vT;
  void main() {
    vT = aT;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position * uScale, 1.0);
  }
`;

const FRAG_ARC = /* glsl */ `
  uniform vec3  uColor;
  uniform float uAlpha;
  uniform float uHead;
  varying float vT;

  void main() {
    float headDist = abs(vT - uHead);
    float trail = smoothstep(0.4, 0.0, headDist);
    float tipGlow = exp(-headDist * headDist * 80.0) * 0.5;
    float alpha = (trail + tipGlow) * uAlpha;
    gl_FragColor = vec4(uColor * alpha * 1.4, alpha);
  }
`;

function lerpN(a, b, t) {
  return a + (b - a) * t;
}

function lerpV3(a, b, t) {
  return [lerpN(a[0], b[0], t), lerpN(a[1], b[1], t), lerpN(a[2], b[2], t)];
}

function heartbeat(t, hz) {
  const p = (t * hz) % 1.0;
  const lub = (p - 0.08) * 18;
  const dub = (p - 0.24) * 18;
  return Math.exp(-(lub * lub)) + Math.exp(-(dub * dub)) * 0.65;
}

function breathe(t, hz) {
  return (
    (Math.sin(t * hz * Math.PI * 2) * 0.5 + 0.5) * 0.85 +
    (Math.sin(t * hz * 1.37 * Math.PI * 2) * 0.15 + 0.15) * 0.15
  );
}

function fibSphere(i, n) {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const theta = golden * i;
  const phi = Math.acos(1 - (2 * (i + 0.5)) / n);
  return [
    Math.sin(phi) * Math.cos(theta),
    Math.cos(phi),
    Math.sin(phi) * Math.sin(theta),
  ];
}

function seededRandom(seed) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randAxis(random = Math.random) {
  const u = random() * 2 - 1;
  const t = random() * Math.PI * 2;
  const s = Math.sqrt(1 - u * u);
  return [s * Math.cos(t), u, s * Math.sin(t)];
}

function slerp(a, b, t) {
  const dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const omega = Math.acos(Math.min(1, Math.max(-1, dot)));
  if (omega < 0.001) return a.map((v, i) => v + (b[i] - v) * t);
  const sinO = Math.sin(omega);
  const sa = Math.sin((1 - t) * omega) / sinO;
  const sb = Math.sin(t * omega) / sinO;
  return [a[0] * sa + b[0] * sb, a[1] * sa + b[1] * sb, a[2] * sa + b[2] * sb];
}

function normalizeState(state) {
  return Object.prototype.hasOwnProperty.call(ORB_STATES, state) ? state : "idle";
}

function cloneConfig(state) {
  const config = ORB_STATES[normalizeState(state)];
  return {
    ...config,
    coreColor: [...config.coreColor],
    particleColor: [...config.particleColor],
    glowColor: [...config.glowColor],
  };
}

function clamp01(value) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

export function createJarvisOrbRenderer(THREE, mount, options = {}) {
  if (!THREE) {
    throw new Error("createJarvisOrbRenderer requires a Three.js namespace");
  }
  if (!mount) {
    throw new Error("createJarvisOrbRenderer requires a mount element");
  }

  const browserWindow = mount.ownerDocument?.defaultView ?? window;
  const browserDocument = mount.ownerDocument ?? document;
  const prefersReducedMotion = browserWindow.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  const initialCompact = browserWindow.matchMedia?.("(max-width: 640px)").matches ?? false;
  const layoutRandom = seededRandom(0x4a415256);
  const clock = new THREE.Clock();

  let isDisposed = false;
  let isVisible = browserDocument.visibilityState !== "hidden";
  let frameId = 0;
  let currentConfig = cloneConfig(options.state);
  let targetConfig = cloneConfig(options.state);
  let audioAmplitude = clamp01(options.audioAmplitude ?? 0);
  let transitionIn = clamp01(options.transitionIn ?? 1);
  const compactPixelRatioCap = options.compactPixelRatioCap ?? 1.35;
  const pixelRatioCap = options.pixelRatioCap ?? 2;
  const particleAlphaScale = options.particleAlphaScale ?? 1;
  const particleSizeScale = options.particleSizeScale ?? 1;
  const glowIntensityScale = options.glowIntensityScale ?? 1;
  const dustAlphaScale = options.dustAlphaScale ?? 1;
  const ringAlphaScale = options.ringAlphaScale ?? 1;

  const effectivePixelRatio = (compact) => {
    if (prefersReducedMotion) return Math.min(browserWindow.devicePixelRatio || 1, compactPixelRatioCap);
    return Math.min(browserWindow.devicePixelRatio || 1, compact ? compactPixelRatioCap : pixelRatioCap);
  };

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: prefersReducedMotion ? "low-power" : "high-performance",
  });
  renderer.setPixelRatio(effectivePixelRatio(initialCompact));
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.style.display = "block";
  renderer.domElement.style.width = "100%";
  renderer.domElement.style.height = "100%";
  mount.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(initialCompact ? 34 : 40, 1, 0.1, 100);
  camera.position.set(0, 0, initialCompact ? 3.05 : 3.5);
  camera.lookAt(0, 0, 0);

  const pos = new Float32Array(PARTICLE_COUNT * 3);
  const sizes = new Float32Array(PARTICLE_COUNT);
  const brights = new Float32Array(PARTICLE_COUNT);
  const shells = new Float32Array(PARTICLE_COUNT);
  const phases = new Float32Array(PARTICLE_COUNT);
  const orbAxes = new Float32Array(PARTICLE_COUNT * 3);

  for (let i = 0; i < PARTICLE_COUNT; i += 1) {
    let shell = 0;
    if (i < SHELL_SPLIT[0]) {
      shell = 0;
    } else if (i < SHELL_SPLIT[1]) {
      shell = 1;
    } else {
      shell = 2;
    }

    let rMin = 0;
    let rMax = 0;
    if (shell === 0) {
      rMin = 0.12;
      rMax = 0.22;
    } else if (shell === 1) {
      rMin = 0.3;
      rMax = 0.5;
    } else {
      rMin = 0.55;
      rMax = 0.85;
    }
    const r = rMin + layoutRandom() * (rMax - rMin);

    const shellBaseIdx = shell === 0 ? 0 : shell === 1 ? 800 : 2000;
    const idxInShell = i - shellBaseIdx;
    const [x, y, z] = fibSphere(idxInShell, SHELL_COUNTS[shell]);

    pos[i * 3] = x * r;
    pos[i * 3 + 1] = y * r;
    pos[i * 3 + 2] = z * r;

    if (shell === 0) {
      sizes[i] = 1.25 + layoutRandom() * 0.85;
      brights[i] = 0.58 + layoutRandom() * 0.16;
    } else if (shell === 1) {
      sizes[i] = 2.0 + layoutRandom() * 1.6;
      brights[i] = 0.48 + layoutRandom() * 0.2;
    } else {
      sizes[i] = 2.8 + layoutRandom() * 2.2;
      brights[i] = 0.36 + layoutRandom() * 0.18;
    }

    shells[i] = shell / 2.0;
    phases[i] = layoutRandom();

    const ax = randAxis(layoutRandom);
    orbAxes[i * 3] = ax[0];
    orbAxes[i * 3 + 1] = ax[1];
    orbAxes[i * 3 + 2] = ax[2];
  }

  const pGeom = new THREE.BufferGeometry();
  pGeom.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  pGeom.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
  pGeom.setAttribute("aBright", new THREE.BufferAttribute(brights, 1));
  pGeom.setAttribute("aShell", new THREE.BufferAttribute(shells, 1));
  pGeom.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
  pGeom.setAttribute("aOrbitAxis", new THREE.BufferAttribute(orbAxes, 3));

  const pMat = new THREE.ShaderMaterial({
    vertexShader: VERT_PARTICLES,
    fragmentShader: FRAG_PARTICLES,
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color() },
      uCoreCol: { value: new THREE.Color() },
      uAlpha: { value: 0.68 },
      uPulse: { value: 0 },
      uScale: { value: 1.0 },
      uAudio: { value: 0 },
      uPointScale: { value: particleSizeScale },
    },
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    depthTest: false,
  });
  scene.add(new THREE.Points(pGeom, pMat));

  const glowMat = new THREE.ShaderMaterial({
    vertexShader: VERT_GLOW,
    fragmentShader: FRAG_GLOW,
    uniforms: {
      uCore: { value: new THREE.Color() },
      uMid: { value: new THREE.Color() },
      uOuter: { value: new THREE.Color() },
      uIntensity: { value: 0.58 },
      uPulse: { value: 0 },
    },
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    depthTest: false,
    side: THREE.DoubleSide,
  });

  const glow1 = new THREE.Mesh(new THREE.PlaneGeometry(1.25, 1.25), glowMat);
  glow1.renderOrder = -2;
  scene.add(glow1);

  const glow2Mat = glowMat.clone();
  const glow2 = new THREE.Mesh(new THREE.PlaneGeometry(2.05, 2.05), glow2Mat);
  glow2.renderOrder = -3;
  scene.add(glow2);

  const dPos = new Float32Array(DUST_COUNT * 3);
  const dSizes = new Float32Array(DUST_COUNT);
  const dPhases = new Float32Array(DUST_COUNT);
  for (let i = 0; i < DUST_COUNT; i += 1) {
    const r = 0.8 + layoutRandom() * 0.6;
    const [x, y, z] = fibSphere(i, DUST_COUNT);
    dPos[i * 3] = x * r;
    dPos[i * 3 + 1] = y * r;
    dPos[i * 3 + 2] = z * r;
    dSizes[i] = 1.0 + layoutRandom() * 2.5;
    dPhases[i] = layoutRandom();
  }
  const dGeom = new THREE.BufferGeometry();
  dGeom.setAttribute("position", new THREE.BufferAttribute(dPos, 3));
  dGeom.setAttribute("aSize", new THREE.BufferAttribute(dSizes, 1));
  dGeom.setAttribute("aPhase", new THREE.BufferAttribute(dPhases, 1));

  const dMat = new THREE.ShaderMaterial({
    vertexShader: VERT_DUST,
    fragmentShader: FRAG_DUST,
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color() },
      uAlpha: { value: 0.18 },
      uScale: { value: 1.0 },
      uPointScale: { value: particleSizeScale },
    },
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    depthTest: false,
  });
  scene.add(new THREE.Points(dGeom, dMat));

  const ringCfg = [
    { r: 0.52, tiltX: 0.25, tiltZ: 0.0, speed: 0.35, segs: 128 },
    { r: 0.42, tiltX: -0.18, tiltZ: 0.12, speed: -0.25, segs: 96 },
    { r: 0.64, tiltX: 0.4, tiltZ: -0.08, speed: 0.18, segs: 160 },
    { r: 0.74, tiltX: -0.1, tiltZ: 0.3, speed: -0.12, segs: 160 },
  ];
  const rings = [];

  for (const rc of ringCfg) {
    const pts = [];
    for (let i = 0; i <= rc.segs; i += 1) {
      const a = (i / rc.segs) * Math.PI * 2;
      pts.push(
        new THREE.Vector3(
          Math.cos(a) * rc.r,
          Math.sin(a) * rc.r * Math.cos(rc.tiltX),
          Math.sin(a) * rc.r * Math.sin(rc.tiltX) + Math.cos(a) * rc.r * Math.sin(rc.tiltZ) * 0.3,
        ),
      );
    }
    const rGeom = new THREE.BufferGeometry().setFromPoints(pts);
    const rMat = new THREE.LineBasicMaterial({
      color: 0x00d4ff,
      transparent: true,
      opacity: 0.12,
      blending: THREE.AdditiveBlending,
    });
    const ring = new THREE.Line(rGeom, rMat);
    scene.add(ring);
    rings.push({ mesh: ring, speed: rc.speed });
  }

  const arcs = [];
  for (let i = 0; i < ARC_COUNT; i += 1) {
    const arcPos = new Float32Array(ARC_PTS * 3);
    const arcT = new Float32Array(ARC_PTS);
    for (let j = 0; j < ARC_PTS; j += 1) arcT[j] = j / (ARC_PTS - 1);

    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(arcPos, 3));
    geom.setAttribute("aT", new THREE.BufferAttribute(arcT, 1));

    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT_ARC,
      fragmentShader: FRAG_ARC,
      uniforms: {
        uColor: { value: new THREE.Color() },
        uAlpha: { value: 0 },
        uScale: { value: 1.0 },
        uHead: { value: 0 },
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      depthTest: false,
    });

    scene.add(new THREE.Line(geom, mat));
    arcs.push({
      geom,
      mat,
      startDir: [0, 1, 0],
      endDir: [1, 0, 0],
      life: 0,
      maxLife: 2,
      active: false,
    });
  }

  const onResize = () => {
    if (isDisposed) return;
    const w = mount.clientWidth || options.width || 260;
    const h = mount.clientHeight || options.height || w;
    if (w <= 0 || h <= 0) return;
    const compact = w < 640 || h < 640;
    camera.fov = compact ? 34 : 40;
    camera.position.z = compact ? 3.05 : 3.5;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(effectivePixelRatio(compact));
    renderer.setSize(w, h);
  };

  const onVisibilityChange = () => {
    isVisible = browserDocument.visibilityState !== "hidden";
    if (isVisible) {
      clock.getDelta();
    }
  };

  browserWindow.addEventListener("resize", onResize);
  browserDocument.addEventListener("visibilitychange", onVisibilityChange);
  onResize();
  clock.start();

  const animate = () => {
    frameId = browserWindow.requestAnimationFrame(animate);
    if (!isVisible || isDisposed) return;

    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;

    const c = currentConfig;
    const g = targetConfig;
    const r = 1 - Math.pow(0.04, dt);

    c.coreColor = lerpV3(c.coreColor, g.coreColor, r);
    c.particleColor = lerpV3(c.particleColor, g.particleColor, r);
    c.glowColor = lerpV3(c.glowColor, g.glowColor, r);
    c.coreIntensity = lerpN(c.coreIntensity, g.coreIntensity, r);
    c.particleAlpha = lerpN(c.particleAlpha, g.particleAlpha, r);
    c.orbitalSpeed = lerpN(c.orbitalSpeed, g.orbitalSpeed, r);
    c.turbulence = lerpN(c.turbulence, g.turbulence, r);
    c.pulseRate = lerpN(c.pulseRate, g.pulseRate, r);
    c.pulseDepth = lerpN(c.pulseDepth, g.pulseDepth, r);
    c.trailStrength = lerpN(c.trailStrength, g.trailStrength, r);
    c.arcFrequency = lerpN(c.arcFrequency, g.arcFrequency, r);
    c.breathBlend = lerpN(c.breathBlend, g.breathBlend, r);
    c.scaleTarget = lerpN(c.scaleTarget, g.scaleTarget, r);
    c.dustAlpha = lerpN(c.dustAlpha, g.dustAlpha, r);
    c.ringAlpha = lerpN(c.ringAlpha, g.ringAlpha, r);

    const hb = heartbeat(t, c.pulseRate);
    const br = breathe(t, c.pulseRate);
    let pulse = hb * (1 - c.breathBlend) + br * c.breathBlend;

    const amp = audioAmplitude;
    if (amp > 0.01) pulse = pulse * 0.15 + amp * 0.85;

    const masterAlpha = transitionIn;

    camera.position.x = Math.sin(t * 0.13) * 0.04;
    camera.position.y = Math.cos(t * 0.09) * 0.03;
    camera.lookAt(0, 0, 0);

    pMat.uniforms.uTime.value = t * c.orbitalSpeed;
    pMat.uniforms.uColor.value.setRGB(c.particleColor[0], c.particleColor[1], c.particleColor[2]);
    pMat.uniforms.uCoreCol.value.setRGB(c.coreColor[0], c.coreColor[1], c.coreColor[2]);
    pMat.uniforms.uAlpha.value = c.particleAlpha * masterAlpha * particleAlphaScale;
    pMat.uniforms.uPulse.value = pulse * c.pulseDepth;
    pMat.uniforms.uScale.value = c.scaleTarget;
    pMat.uniforms.uAudio.value = amp;

    const glowUpdater = (mat, intensityMul) => {
      mat.uniforms.uCore.value.setRGB(c.coreColor[0], c.coreColor[1], c.coreColor[2]);
      mat.uniforms.uMid.value.setRGB(c.particleColor[0], c.particleColor[1], c.particleColor[2]);
      mat.uniforms.uOuter.value.setRGB(c.glowColor[0], c.glowColor[1], c.glowColor[2]);
      mat.uniforms.uIntensity.value = c.coreIntensity * masterAlpha * intensityMul * glowIntensityScale * (1 + pulse * 0.2);
      mat.uniforms.uPulse.value = pulse;
    };
    glowUpdater(glowMat, 0.76);
    glowUpdater(glow2Mat, 0.34);

    glow1.quaternion.copy(camera.quaternion);
    glow2.quaternion.copy(camera.quaternion);

    dMat.uniforms.uTime.value = t;
    dMat.uniforms.uColor.value.setRGB(c.particleColor[0], c.particleColor[1], c.particleColor[2]);
    dMat.uniforms.uAlpha.value = c.dustAlpha * masterAlpha * dustAlphaScale;
    dMat.uniforms.uScale.value = c.scaleTarget;

    for (const rd of rings) {
      rd.mesh.rotation.y += rd.speed * dt * c.orbitalSpeed * 4;
      rd.mesh.rotation.x += rd.speed * dt * c.orbitalSpeed * 0.8;
      const mat = rd.mesh.material;
      mat.color.setRGB(c.particleColor[0], c.particleColor[1], c.particleColor[2]);
      mat.opacity = c.ringAlpha * masterAlpha * ringAlphaScale * (0.6 + pulse * 0.4);
    }

    for (const arc of arcs) {
      if (arc.active) {
        arc.life += dt;
        if (arc.life >= arc.maxLife) {
          arc.active = false;
          arc.mat.uniforms.uAlpha.value = 0;
          continue;
        }
        const prog = arc.life / arc.maxLife;
        const fadeIn = Math.min(prog * 6, 1);
        const fadeOut = 1 - Math.max(0, (prog - 0.6) / 0.4);
        arc.mat.uniforms.uAlpha.value = fadeIn * fadeOut * c.trailStrength * masterAlpha * 0.7;
        arc.mat.uniforms.uColor.value.setRGB(c.particleColor[0], c.particleColor[1], c.particleColor[2]);
        arc.mat.uniforms.uScale.value = c.scaleTarget;
        arc.mat.uniforms.uHead.value = prog;

        const posAttr = arc.geom.getAttribute("position");
        for (let j = 0; j < ARC_PTS; j += 1) {
          const frac = j / (ARC_PTS - 1);
          const pt = slerp(arc.startDir, arc.endDir, frac);
          const bulge = 1.0 + Math.sin(frac * Math.PI) * 0.18;
          const radius = 0.55 * bulge;
          posAttr.setXYZ(j, pt[0] * radius, pt[1] * radius, pt[2] * radius);
        }
        posAttr.needsUpdate = true;
      }

      if (!arc.active && c.arcFrequency > 0 && Math.random() < c.arcFrequency * dt) {
        arc.active = true;
        arc.life = 0;
        arc.maxLife = 1.2 + Math.random() * 1.6;
        arc.startDir = randAxis();
        arc.endDir = randAxis();
      }
    }

    renderer.render(scene, camera);
  };

  frameId = browserWindow.requestAnimationFrame(animate);

  return {
    setState(nextState) {
      targetConfig = cloneConfig(nextState);
    },
    setAudioAmplitude(nextAmplitude) {
      audioAmplitude = clamp01(nextAmplitude);
    },
    setTransitionIn(nextTransition) {
      transitionIn = clamp01(nextTransition);
    },
    resize() {
      onResize();
    },
    dispose() {
      if (isDisposed) return;
      isDisposed = true;
      browserWindow.cancelAnimationFrame(frameId);
      browserWindow.removeEventListener("resize", onResize);
      browserDocument.removeEventListener("visibilitychange", onVisibilityChange);
      renderer.dispose();
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
      pGeom.dispose();
      pMat.dispose();
      glow1.geometry.dispose();
      glowMat.dispose();
      glow2.geometry.dispose();
      glow2Mat.dispose();
      dGeom.dispose();
      dMat.dispose();
      for (const rd of rings) {
        rd.mesh.geometry.dispose();
        rd.mesh.material.dispose();
      }
      for (const arc of arcs) {
        arc.geom.dispose();
        arc.mat.dispose();
      }
    },
  };
}
