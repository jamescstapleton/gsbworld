// GSB campus game: loads gsb_campus.glb (exported by gsb_campus.py with
// EXPORT_GLB = "web/gsb_campus.glb"), lights it with a regular sun, darkens
// everything by distance from Town Square with a small shader patch, and adds
// the walking-tree player (player.js) and the campus crowd (people.js).
//
// Serve this folder over http (browsers block loading the .glb from file://):
//   python -m http.server 8000      then open http://localhost:8000

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createPlayer } from "./player.js";
import { createPeople, mapToWorld } from "./people.js";
import { createChat } from "./chat.js";
import { createSeating } from "./seating.js";

// ---------------------------------------------------------------- settings
// glTF is Y-up: Blender (x, y, z) becomes (x, z, -y), so north is -Z.
const TOWN_SQUARE = new THREE.Vector2(-0.25, 1.0); // (x, z) of the Town Square center
const FALLOFF = {
  radiusEW: 160,   // meters east-west where light reaches its darkest
  radiusNS: 95,    // meters north-south (the grey blocks start ~85 m south)
  inner: 0.3,      // fraction of the radius that stays fully lit
  floor: 0.08,     // brightness left at and beyond the edge (0 = black)
};
const SUN = {
  elevationDeg: 55,
  azimuthDeg: 200, // compass direction of the sun (180 = due south)
  intensity: 3.2,
  color: 0xfff2db,
};
const SKY = { zenith: 0x265fc4, horizon: 0x94bff2, below: 0x82a3cf };
const MIN_INSTANCES = 2; // shared meshes used at least this often become InstancedMesh
const GAME = {
  start: mapToWorld(1060, 440), // on Knight Way in front of Patterson, between the grass mounds
  facing: -Math.PI / 2,         // looking west down Knight Way toward Arbuckle
  people: 120,
  seatedShare: 0.2,             // fraction of people sitting at the Arbuckle tables
  localShare: 0.8,              // fraction of walkers who stay around Town Square
  // must follow FURNITURE["scale"] in gsb_campus.py (seat 0.45 m x 1.5)
  seatHeight: 0.7,              // where seated people's hips rest
  seatBack: 0.12,               // seated people sit this far back from the chair center
  emptyTables: 5,               // tables kept free so the tree can sit down
};
const CUTOUT_MATERIALS = ["GSB_louver", "GSB_iron_mesh"]; // alpha-cut slats and wire mesh

// ---------------------------------------------------------------- renderer, scene, camera
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(SKY.horizon, 350, 1100);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.3, 4000);

// Orbit camera centered on the player (player.js moves the target along).
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.enablePan = false;
controls.maxPolarAngle = Math.PI * 0.48; // stay above the ground
controls.minDistance = 4;
controls.maxDistance = 300;

// ---------------------------------------------------------------- sky
// Gradient dome drawn in sRGB directly (not tone mapped, not darkened).
const skyMaterial = new THREE.ShaderMaterial({
  side: THREE.BackSide,
  depthWrite: false,
  fog: false,
  uniforms: {
    zenith: { value: new THREE.Color(SKY.zenith).convertLinearToSRGB() },
    horizon: { value: new THREE.Color(SKY.horizon).convertLinearToSRGB() },
    below: { value: new THREE.Color(SKY.below).convertLinearToSRGB() },
  },
  vertexShader: /* glsl */ `
    varying vec3 vDir;
    void main() {
      vDir = normalize(position);
      vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      gl_Position = p.xyww; // always at the far plane
    }`,
  fragmentShader: /* glsl */ `
    uniform vec3 zenith, horizon, below;
    varying vec3 vDir;
    void main() {
      float h = vDir.y;
      vec3 c = h > 0.0 ? mix(horizon, zenith, pow(h, 0.6)) : mix(horizon, below, clamp(-h * 8.0, 0.0, 1.0));
      gl_FragColor = vec4(c, 1.0);
    }`,
});
const sky = new THREE.Mesh(new THREE.SphereGeometry(3000, 32, 16), skyMaterial);
sky.renderOrder = -1;
sky.frustumCulled = false;
scene.add(sky);

// ---------------------------------------------------------------- lights
const e = THREE.MathUtils.degToRad(SUN.elevationDeg);
const a = THREE.MathUtils.degToRad(SUN.azimuthDeg);
// compass (east, north, up) -> three (x, y, z) = (east, up, -north)
const toSun = new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), -Math.cos(a) * Math.cos(e));

const sun = new THREE.DirectionalLight(SUN.color, SUN.intensity);
sun.position.set(TOWN_SQUARE.x, 0, TOWN_SQUARE.y).addScaledVector(toSun, 400);
sun.target.position.set(TOWN_SQUARE.x, 0, TOWN_SQUARE.y);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
Object.assign(sun.shadow.camera, { left: -220, right: 220, top: 220, bottom: -220, near: 50, far: 800 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.4;
scene.add(sun, sun.target);

scene.add(new THREE.HemisphereLight(SKY.horizon, 0x6b6250, 0.9)); // sky fill

// ---------------------------------------------------------------- distance darkening
// Patched into every lit material: multiplies the final lit color by a falloff
// that is 1 inside `inner` of an ellipse around Town Square and eases down to
// `floor` at its edge. Works for InstancedMesh too.
const falloffUniforms = {
  gsbCenter: { value: TOWN_SQUARE },
  gsbRadius: { value: new THREE.Vector2(FALLOFF.radiusEW, FALLOFF.radiusNS) },
  gsbInner: { value: FALLOFF.inner },
  gsbFloor: { value: FALLOFF.floor },
};

function addDistanceFalloff(material) {
  if (material.userData.gsbFalloff) return;
  material.userData.gsbFalloff = true;
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, falloffUniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vGsbWorld;")
      .replace("#include <project_vertex>", `#include <project_vertex>
        vec4 gsbWorld = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          gsbWorld = instanceMatrix * gsbWorld;
        #endif
        vGsbWorld = (modelMatrix * gsbWorld).xyz;`);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>
        varying vec3 vGsbWorld;
        uniform vec2 gsbCenter, gsbRadius;
        uniform float gsbInner, gsbFloor;`)
      .replace("#include <tonemapping_fragment>", `
        float gsbD = length((vGsbWorld.xz - gsbCenter) / gsbRadius);
        gl_FragColor.rgb *= mix(gsbFloor, 1.0, 1.0 - smoothstep(gsbInner, 1.0, gsbD));
        #include <tonemapping_fragment>`);
  };
  material.needsUpdate = true;
}

// ---------------------------------------------------------------- instancing
// Meshes that share the same geometry and material (trees, shrubs) are folded
// into one InstancedMesh each: one draw call per kind instead of one per plant.
function instanceRepeatedMeshes(root) {
  root.updateMatrixWorld(true);
  const groups = new Map();
  root.traverse((obj) => {
    if (!obj.isMesh || obj.isInstancedMesh) return;
    const key = obj.geometry.uuid + "|" + obj.material.uuid;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(obj);
  });

  let instanced = 0, draws = 0;
  for (const meshes of groups.values()) {
    if (meshes.length < MIN_INSTANCES) continue;
    const { geometry, material } = meshes[0];
    const inst = new THREE.InstancedMesh(geometry, material, meshes.length);
    inst.name = (meshes[0].parent?.name || meshes[0].name).replace(/_\d+$/, "") + "_instanced";
    meshes.forEach((m, i) => inst.setMatrixAt(i, m.matrixWorld));
    inst.instanceMatrix.needsUpdate = true;
    inst.computeBoundingSphere();
    inst.castShadow = inst.receiveShadow = true;
    scene.add(inst);
    for (const m of meshes) m.removeFromParent();
    instanced += meshes.length;
    draws += 1;
  }
  return { instanced, draws };
}

// ---------------------------------------------------------------- tables and seats
// Chairs are named Chair_TT_K and tables Table_TT by gsb_campus.py. Each chair
// gets the spot and heading someone sitting in it would use.
function findTables(root) {
  root.updateMatrixWorld(true);
  const byId = {};
  root.traverse((o) => {
    const t = o.name.match(/^Table_(\d+)$/);
    if (t) (byId[t[1]] ??= { id: t[1], chairs: [] }).pos = o.getWorldPosition(new THREE.Vector3());
  });
  root.traverse((o) => {
    const c = o.name.match(/^Chair_(\d+)_\d+$/);
    const table = c && byId[c[1]];
    if (!table) return;
    const pos = o.getWorldPosition(new THREE.Vector3());
    const toTable = table.pos.clone().sub(pos).setY(0).normalize();
    table.chairs.push({
      table,
      pos,
      toTable,
      seat: pos.clone().addScaledVector(toTable, -GAME.seatBack).setY(0), // where the sitter's feet go
      yaw: Math.atan2(toTable.x, toTable.z),
      occupied: false,
    });
  });
  return Object.values(byId);
}

const shuffle = (a) => {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

// Seat n people in random chairs, but leave GAME.emptyTables tables free for the tree.
function chooseSeats(tables, n) {
  const usable = shuffle([...tables]).slice(GAME.emptyTables);
  const chairs = shuffle(usable.flatMap((t) => t.chairs)).slice(0, n);
  return chairs.map((c) => {
    c.occupied = true;
    return { position: c.seat, yaw: c.yaw, height: GAME.seatHeight };
  });
}

// ---------------------------------------------------------------- load
const hint = document.getElementById("hint");
let player = null, people = null, chat = null, seating = null;

// Space talks (chat.js) first; otherwise it sits down (seating.js).
window.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || e.repeat || !chat) return;
  e.preventDefault();
  if (!chat.handleSpace()) seating.handleSpace();
});
new GLTFLoader().load(
  "gsb_campus.glb",
  (gltf) => {
    const campus = gltf.scene;
    scene.add(campus);
    const tables = findTables(campus); // before instancing removes the named chairs
    const seats = chooseSeats(tables, Math.round(GAME.people * GAME.seatedShare));
    const { instanced, draws } = instanceRepeatedMeshes(campus);

    const maxAniso = renderer.capabilities.getMaxAnisotropy();
    scene.traverse((obj) => {
      if (!obj.isMesh || obj === sky) return;
      obj.castShadow = obj.receiveShadow = true;
      const mat = obj.material;
      if (mat.map) mat.map.anisotropy = maxAniso; // keeps facades sharp at grazing angles
      if (CUTOUT_MATERIALS.includes(mat.name)) {    // slats / wire mesh: cut-out, not blended
        mat.transparent = false;
        mat.alphaTest = 0.5;
        mat.alphaToCoverage = true;                  // smooth edges with MSAA, less shimmer far away
        mat.depthWrite = true;
        if (mat.map) {                               // the tiny patterns export as nearest-neighbor
          mat.map.magFilter = THREE.LinearFilter;
          mat.map.minFilter = THREE.LinearMipmapLinearFilter;
          mat.map.needsUpdate = true;
        }
      }
      addDistanceFalloff(mat);
    });

    // everything in the campus can block the player (flat ground never hits a horizontal ray)
    const collidables = [];
    scene.traverse((o) => { if (o.isMesh && o !== sky) collidables.push(o); });

    player = createPlayer(scene, {
      start: GAME.start, facing: GAME.facing, camera, controls, collidables,
      patchMaterial: addDistanceFalloff,
    });
    people = createPeople(scene, {
      walkers: GAME.people - seats.length, seats, localShare: GAME.localShare,
      patchMaterial: addDistanceFalloff,
    });
    chat = createChat({ camera, controls, player, people });
    hint.textContent = "WASD to walk · arrows to hurry · Shift to run · Space to talk or sit · drag to look · scroll to zoom";
    seating = createSeating({ camera, controls, player, people, chat, tables, seatHeight: GAME.seatHeight, hint });
    // for the browser console; gsb.frame(dt) advances and draws one frame by hand
    window.gsb = { THREE, scene, camera, controls, player, people, chat, seating, tables, collidables, seats, frame };

    console.log(`GSB: ${instanced} meshes folded into ${draws} InstancedMesh draws; ` +
                `${people.count} people (${seats.length} seated); ` +
                `${tables.filter((t) => t.chairs.every((c) => !c.occupied)).length} empty tables`);
  },
  undefined,
  (err) => {
    console.error(err);
    hint.textContent = "Could not load gsb_campus.glb. Serve this folder over http (see main.js).";
  },
);

// ---------------------------------------------------------------- loop
window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => frame(Math.min(clock.getDelta(), 0.05)));

function frame(dt) {
  player?.update(dt);
  people?.update(dt);
  seating?.update(dt);                     // drives the camera while sitting
  chat?.update(dt);                        // drives the camera during a chat
  if (controls.enabled) controls.update();
  sky.position.copy(camera.position);
  renderer.render(scene, camera);
}
