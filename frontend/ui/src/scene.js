import * as THREE from 'three';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

const BufferGeometryUtils = { mergeVertices };

export function mountScene(canvas) {
  if (!canvas) return () => {};
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.06;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
camera.position.set(0, 0, 21);

/* ------- colourful studio environment (the iridescent look lives here) ------- */
function makeEnvironment() {
  const envScene = new THREE.Scene();
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    vertexShader: /* glsl */ `
      varying vec3 vPos;
      void main() {
        vPos = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      varying vec3 vPos;
      void main() {
        vec3 d = normalize(vPos);
        float u = atan(d.z, d.x);
        float v = d.y;
        // --- fully chromatic dome: every reflection direction lands on colour,
        // not on neutral grey (a grey base is what washes the slabs out)
        float mixer = 0.5 + 0.5 * cos(u - 0.55);          // smooth wrap, no seam
        vec3 cool = vec3(0.02, 0.88, 1.05);               // turquoise half
        vec3 warm = vec3(1.05, 0.22, 0.86);               // magenta half
        vec3 chroma = mix(cool, warm, mixer);
        chroma = mix(chroma, vec3(0.42, 0.20, 1.05),      // violet wedge behind
                     0.55 * exp(-pow((u + 2.55) / 0.85, 2.0)));

        // vertical ramp: deep at the floor, bright near the ceiling
        vec3 col = chroma * mix(0.36, 1.62, smoothstep(-0.80, 0.72, v));

        // --- narrow softbox strips: these draw the crisp rim streaks
        col += vec3(1.00, 0.99, 0.97) * 4.60 * exp(-pow((v - 0.58) / 0.030, 2.0));
        col += vec3(0.97, 0.99, 1.00) * 2.60 * exp(-pow((v - 0.24) / 0.024, 2.0));
        col += vec3(1.00, 0.96, 0.99) * 1.00 * exp(-pow((v + 0.06) / 0.024, 2.0));
        col += vec3(0.72, 0.88, 1.00) * 0.55 * exp(-pow((v + 0.44) / 0.060, 2.0));

        // --- vertical slats break the strips up so streaks vary along the chain
        float slat = 0.5 + 0.5 * sin(u * 5.0 + 1.2);
        col *= 1.0 + 0.28 * slat * exp(-pow((v - 0.30) / 0.55, 2.0));

        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  envScene.add(new THREE.Mesh(new THREE.SphereGeometry(50, 64, 32), mat));
  const pmrem = new THREE.PMREMGenerator(renderer);
  const tex = pmrem.fromScene(envScene, 0.012).texture;
  pmrem.dispose();
  envScene.children[0].geometry.dispose();
  mat.dispose();
  return tex;
}
scene.environment = makeEnvironment();

const key = new THREE.DirectionalLight(0xffffff, 1.35);
key.position.set(2.5, 6, 5);
scene.add(key);
// grazing spec light along the chain: lifts every rim into a bright line
const rim = new THREE.DirectionalLight(0xeaf4ff, 0.85);
rim.position.set(-4, 3.5, 1.5);
scene.add(rim);
const magenta = new THREE.DirectionalLight(0xff5ccd, 0.55);
magenta.position.set(-6, 1, 4);
scene.add(magenta);
const cyan = new THREE.DirectionalLight(0x1fd0ff, 1.55);
cyan.position.set(6, -1.5, 4);
scene.add(cyan);
// cool bounce from below keeps undersides from going muddy
const bounce = new THREE.DirectionalLight(0xa9c8f5, 0.35);
bounce.position.set(0, -6, 2);
scene.add(bounce);
scene.add(new THREE.AmbientLight(0xbfd0e8, 0.05));

/* ------- slab geometry: rounded card, top edge on the chain axis ------- */
function makeSlabGeometry() {
  const w = 3.4, h = 2.4, r = 0.5;
  const shape = new THREE.Shape();
  const x = -w / 2, y = -h;
  shape.moveTo(x + r, y);
  shape.lineTo(x + w - r, y);
  shape.absarc(x + w - r, y + r, r, -Math.PI / 2, 0);
  shape.lineTo(x + w, y + h - r);
  shape.absarc(x + w - r, y + h - r, r, 0, Math.PI / 2);
  shape.lineTo(x + r, y + h);
  shape.absarc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
  shape.lineTo(x, y + r);
  shape.absarc(x + r, y + r, r, Math.PI, Math.PI * 1.5);

  let geo = new THREE.ExtrudeGeometry(shape, {
    depth: 0.05,
    bevelEnabled: true,
    bevelThickness: 0.055,
    bevelSize: 0.05,
    bevelSegments: 5,
    curveSegments: 16,
  });
  geo = BufferGeometryUtils.mergeVertices(geo, 1e-4);
  geo.computeVertexNormals();
  geo.translate(0, 0.1, -0.025); // top edge rides just above the chain axis

  // cheap baked AO: back face and spine area darker, so crevices between
  // fanned slabs read as shadowed slots like in the reference render
  const pos = geo.getAttribute('position');
  const colors = new Float32Array(pos.count * 3);
  const zMin = -0.025 - 0.055, zMax = 0.05 + 0.055 - 0.025;
  for (let i = 0; i < pos.count; i++) {
    const z = pos.getZ(i), y = pos.getY(i);
    const front = (z - zMin) / (zMax - zMin);      // 0 back … 1 front
    let v = 0.38 + 0.62 * front;
    const spine = 1 - Math.min(1, Math.max(0, (-y - 0.15) / 0.75));
    v *= 1 - 0.30 * spine;
    colors[i * 3] = colors[i * 3 + 1] = colors[i * 3 + 2] = v;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  // face the card across the chain axis (CD-on-spindle stacking, not flags)
  geo.rotateY(Math.PI / 2);
  return geo;
}

const material = new THREE.MeshPhysicalMaterial({
  color: 0xffffff,
  vertexColors: true,
  metalness: 0.45,
  roughness: 0.085,
  clearcoat: 1.0,
  clearcoatRoughness: 0.022,
  envMapIntensity: 1.55,
  specularIntensity: 1.30,
  iridescence: 1.0,
  iridescenceIOR: 1.35,
  iridescenceThicknessRange: [180, 780],
});

const COUNT = 110;
const SPACING = 0.52;
const chain = new THREE.InstancedMesh(makeSlabGeometry(), material, COUNT);
chain.frustumCulled = false;
{
  // pastel tint drift along the chain: pink / cyan / lavender patches
  const pink = new THREE.Color('#f78fe2');
  const cyanT = new THREE.Color('#12dced');
  const lav = new THREE.Color('#a48bf2');
  const white = new THREE.Color('#ffffff');
  const c = new THREE.Color();
  for (let i = 0; i < COUNT; i++) {
    const a = 0.5 + 0.5 * Math.sin(i * 0.17 + 1.3);
    const b = 0.5 + 0.5 * Math.sin(i * 0.08 - 0.6);
    // third oscillator: some runs bleach toward silver-white, some stay vivid
    const w = 0.06 + 0.52 * Math.pow(0.5 + 0.5 * Math.sin(i * 0.105 + 2.2), 2.0);
    c.copy(cyanT).lerp(pink, a * 0.44).lerp(lav, b * 0.22).lerp(white, w);
    chain.setColorAt(i, c);
  }
  chain.instanceColor.needsUpdate = true;
}
scene.fog = new THREE.Fog(0xf1f1f3, 28, 52);
const group = new THREE.Group();
group.add(chain);
scene.add(group);

const dummy = new THREE.Object3D();
/* Helix: every card is a tread on a spiral staircase. The chain axis runs along
   local X with only a gentle bow; each card hangs from the axis and is rotated
   about it by a STEADY step, so the tips trace a true helix — sweeping toward the
   camera on one side and away on the other. The whole spiral turns slowly with
   time, which is what keeps it kinetic without any ribbon-like waving. */
const HELIX_STEP = 0.135;      // radians per card (~7.7°): ~2.4 turns along the chain
const HELIX_BASE = -0.9;
const HELIX_TURN = 0.42;       // radians of continuous rotation per phase unit
function layoutChain(phase) {
  for (let i = 0; i < COUNT; i++) {
    const t = i - COUNT / 2;
    dummy.position.set(
      t * SPACING,
      0.42 * Math.sin(t * 0.085),          // gentle S along the axis (static)
      0.22 * Math.sin(t * 0.06 + 1.2),     // slight bow in depth
    );
    const angle =
      HELIX_BASE +
      i * HELIX_STEP +
      phase * HELIX_TURN +
      0.05 * Math.sin(i * 0.21 - phase * 0.9);   // faint breathing, keeps spacing consistent
    dummy.rotation.set(angle, 0, 0);
    dummy.updateMatrix();
    chain.setMatrixAt(i, dummy.matrix);
  }
  chain.instanceMatrix.needsUpdate = true;
}

/* ------- scroll choreography -------
   One pose per section, keyed by element id. The keyframe times are derived
   from where each section actually sits, so the helix stays in step with the
   layout instead of assuming every section is exactly one viewport tall.     */
const POSES = {
  hero:         { px:  0.0, py:  1.3, pz:  0.0, rx:  0.30, ry:  0.22, rz: -0.62, ph: 0.0 },
  features:     { px:  0.8, py: -5.0, pz:  0.6, rx: -0.20, ry:  0.18, rz: -0.34, ph: 1.6 },
  showcase:     { px:  6.4, py:  0.6, pz:  1.2, rx:  0.55, ry:  0.10, rz: -1.32, ph: 2.9 },
  gallery:      { px: -1.0, py:  6.9, pz:  1.0, rx:  1.30, ry:  0.15, rz: -0.28, ph: 4.1 },
  timeline:     { px:  1.2, py: -7.2, pz:  0.4, rx: -0.34, ry:  0.20, rz: -0.40, ph: 5.3 },
  pricing:      { px: -7.8, py:  9.8, pz:  1.6, rx:  0.95, ry:  0.12, rz: -0.62, ph: 6.4 },
  testimonials: { px:  0.6, py: -5.8, pz:  0.8, rx: -0.16, ry:  0.18, rz: -0.30, ph: 7.6 },
  faq:          { px: -0.8, py:  6.4, pz:  1.0, rx:  1.25, ry:  0.15, rz: -0.30, ph: 8.7 },
  cta:          { px:  0.2, py:  6.8, pz:  0.2, rx:  0.26, ry:  0.20, rz: -0.58, ph: 9.8 },
  contact:      { px:  0.0, py:  8.6, pz:  0.6, rx:  1.10, ry:  0.16, rz: -0.44, ph: 10.6 },
};
const KEYS = ['px', 'py', 'pz', 'rx', 'ry', 'rz', 'ph'];

let KF = [];
function buildKeyframes() {
  const vh = window.innerHeight;
  KF = [];
  for (const [id, pose] of Object.entries(POSES)) {
    const el = document.getElementById(id);
    if (!el) continue;
    const rect = el.getBoundingClientRect();
    const top = rect.top + window.scrollY;
    // aim the pose at the moment the section is centred in the viewport
    const centre = top + Math.min(rect.height, vh * 1.4) / 2 - vh / 2;
    KF.push({ t: Math.max(0, centre) / vh, ...pose });
  }
  KF.sort((a, b) => a.t - b.t);
}

const smooth = (a) => a * a * (3 - 2 * a);
function sampleKF(t) {
  if (!KF.length) return { ...POSES.hero };
  if (t <= KF[0].t) return { ...KF[0] };
  if (t >= KF[KF.length - 1].t) return { ...KF[KF.length - 1] };
  let i = 0;
  while (KF[i + 1].t < t) i++;
  const a = KF[i], b = KF[i + 1];
  const f = smooth((t - a.t) / Math.max(1e-6, b.t - a.t));
  const out = {};
  for (const k of KEYS) out[k] = a[k] + (b[k] - a[k]) * f;
  return out;
}

function applyState(scrollPx, time) {
  const s = sampleKF(scrollPx / window.innerHeight);
  group.position.set(s.px, s.py, s.pz);
  group.rotation.set(s.rx, s.ry, s.rz);
  layoutChain(time * 0.55 + s.ph);
}

/* ------- sizing ------- */
const BASE_Z = 21;
function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  // fov is vertical, so a narrow viewport crops the chain horizontally and the
  // helix swamps the text. Dolly back as the frame narrows (no-op on desktop).
  camera.position.z = BASE_Z * Math.max(1, Math.pow(1.15 / camera.aspect, 0.65));
  camera.updateProjectionMatrix();
  buildKeyframes();
}
window.addEventListener('resize', resize);
resize();


  let frameId = 0;
  let smoothY = window.scrollY;
  let last = performance.now();
  function loop(now) {
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    smoothY += (window.scrollY - smoothY) * (1 - Math.exp(-dt * 6));
    applyState(smoothY, now / 1000);
    renderer.render(scene, camera);
    frameId = requestAnimationFrame(loop);
  }
  frameId = requestAnimationFrame(loop);

  return () => {
    cancelAnimationFrame(frameId);
    window.removeEventListener('resize', resize);
    chain.geometry.dispose();
    material.dispose();
    scene.environment?.dispose();
    renderer.dispose();
  };
}
