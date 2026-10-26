// Low-poly people: walkers that wander a path network slowly and sometimes stop,
// plus people sitting on the cafe chairs under the Arbuckle pergola.
//
// Every body part is one InstancedMesh shared by all people (heads, torsos,
// arms, legs), so ~120 animated people cost 4 draw calls.

import * as THREE from "three";

// ---------------------------------------------------------------- path network
// Map pixels on the directory map (same coordinates as gsb_campus.py).
// Walkers move between connected nodes with a small sideways offset.
const NODES = {
  // Knight Way, along its north edge (south of the pergola)
  k262: [262, 402], k340: [340, 402], k430: [430, 402], k520: [520, 402], k606: [606, 402],
  k700: [700, 402], k800: [800, 402], k892: [892, 402], k980: [980, 402], k1080: [1080, 402],
  k1180: [1180, 402], k1215: [1215, 402],
  // Town Square: a loop just inside the tree rows, a center, and the strip below Bass
  ts345: [600, 345], ts285: [600, 285], tsNW: [568, 268], tsNE: [622, 268], tsSE: [622, 382],
  tsSW: [568, 382], tsW: [568, 325], tsE: [622, 325], tsBass: [600, 245],
  // King Community Court
  kc350: [340, 350], kc290: [340, 290],
  // McCoy Courtyard, reached between Botha-Chan South and Faculty East South
  mc330: [892, 330], mc280: [892, 280], mc780: [780, 280], mc1000: [1000, 280], mc1070: [1070, 280],
  // cross paths down to Jane Stanford Way
  gm470: [280, 470], gm540: [280, 540], w470: [606, 470], w540: [606, 540],
  cp470: [887, 470], cp540: [887, 540], e470: [1180, 470], e540: [1180, 540],
  // Jane Stanford Way
  j150: [150, 604], j280: [280, 604], j450: [450, 604], j606: [606, 604], j750: [750, 604],
  j887: [887, 604], j1030: [1030, 604], j1180: [1180, 604], j1320: [1320, 604],
};
const EDGES = [
  "k262-k340", "k340-k430", "k430-k520", "k520-k606", "k606-k700", "k700-k800", "k800-k892",
  "k892-k980", "k980-k1080", "k1080-k1180", "k1180-k1215",
  "k606-ts345", "ts345-ts285", "k340-kc350", "kc350-kc290",
  "tsNW-tsNE", "tsNE-tsE", "tsE-tsSE", "tsSE-tsSW", "tsSW-tsW", "tsW-tsNW",
  "tsW-ts345", "tsE-ts345", "tsW-ts285", "tsE-ts285", "ts285-tsBass", "tsNW-tsBass", "tsNE-tsBass",
  "tsSW-k606", "tsSE-k606", "tsSE-k700",
  "k892-mc330", "mc330-mc280", "mc780-mc280", "mc280-mc1000", "mc1000-mc1070",
  "k262-gm470", "gm470-gm540", "gm540-j280", "k606-w470", "w470-w540", "w540-j606",
  "k892-cp470", "cp470-cp540", "cp540-j887", "k1180-e470", "e470-e540", "e540-j1180",
  "j150-j280", "j280-j450", "j450-j606", "j606-j750", "j750-j887", "j887-j1030",
  "j1030-j1180", "j1180-j1320",
];

export function mapToWorld(x, y) {
  return new THREE.Vector3((x - 595) * 0.25, 0, (y - 320) * 0.25);
}

const nodePos = {};
const neighbors = {};
for (const [name, [x, y]] of Object.entries(NODES)) {
  nodePos[name] = mapToWorld(x, y);
  neighbors[name] = [];
}
for (const e of EDGES) {
  const [a, b] = e.split("-");
  neighbors[a].push(b);
  neighbors[b].push(a);
}

// "Locals" stay on the part of the network near Town Square; the rest roam the campus.
const TOWN_SQUARE = mapToWorld(595, 325);
const LOCAL_RADIUS = 40; // meters
const isLocal = (n) => nodePos[n].distanceTo(TOWN_SQUARE) < LOCAL_RADIUS;
const localNodes = Object.keys(NODES).filter(isLocal);

// ---------------------------------------------------------------- look
const SKIN = [0xf1c27d, 0xe0ac69, 0xc68642, 0x8d5524, 0xffdbac, 0x5c3a1e];
const SHIRTS = [0xc0392b, 0x2e86c1, 0x27ae60, 0xf1c40f, 0x8e44ad, 0xecf0f1, 0x34495e, 0xe67e22, 0x16a085, 0xd35400];
const PANTS = [0x2c3e50, 0x34495e, 0x1b2631, 0x5d6d7e, 0x6e2c00, 0x283747, 0x7f8c8d];

// Body layout in meters, feet at y = 0, facing +Z.
const HIP_Y = 0.85, SHOULDER_Y = 1.42, LEG_X = 0.09, ARM_X = 0.25;
const SEATED_LEGS = -1.35; // thighs nearly level, feet a little lower (radians from hanging)
const SEATED_ARMS = -1.2;  // forearms resting on the table top
const VISIT_SPEED = 4;   // m/s: visitors walk over a bit quicker than a stroll
const REVISIT_MS = 60000;  // a visitor won't be picked again for a minute

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const rand = (a, b) => a + Math.random() * (b - a);

// Where a walker at `node` (arriving from `came`) may go next: not straight back
// unless it's a dead end, and locals only along edges that stay near Town Square.
function nextOptions(p, node, came) {
  let options = neighbors[node];
  if (p.local) options = options.filter(isLocal);
  const forward = options.filter((n) => n !== came);
  return forward.length ? forward : options.length ? options : neighbors[node];
}

export function createPeople(scene, { walkers = 100, seats = [], localShare = 0.8, patchMaterial }) {
  const count = walkers + seats.length;
  const mat = () => {
    const m = new THREE.MeshStandardMaterial({ roughness: 0.8, flatShading: true });
    patchMaterial?.(m);
    return m;
  };
  const legGeo = new THREE.BoxGeometry(0.14, 0.82, 0.16).translate(0, -0.41, 0);  // pivot at hip
  const armGeo = new THREE.BoxGeometry(0.09, 0.58, 0.1).translate(0, -0.29, 0);   // pivot at shoulder
  const torsoGeo = new THREE.BoxGeometry(0.4, 0.6, 0.24);
  const headGeo = new THREE.IcosahedronGeometry(0.13, 0);

  const make = (geo, n) => {
    const m = new THREE.InstancedMesh(geo, mat(), n);
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.castShadow = true;
    m.frustumCulled = false; // instances move around; one bounding sphere would go stale
    scene.add(m);
    return m;
  };
  const heads = make(headGeo, count), torsos = make(torsoGeo, count);
  const arms = make(armGeo, count * 2), legs = make(legGeo, count * 2);

  // ---- people state
  const people = [];
  const nodeNames = Object.keys(NODES);
  for (let i = 0; i < count; i++) {
    const seat = i >= walkers ? seats[i - walkers] : null;
    const p = {
      seated: !!seat,
      pos: new THREE.Vector3(),
      yaw: 0,
      scale: rand(0.9, 1.08),
      speed: rand(0.4, 0.8),      // m/s: slow stroll
      offset: rand(-1.0, 1.0),    // sideways lane offset
      phase: rand(0, Math.PI * 2),
      swing: 0,
      wait: 0,
      from: null, to: null,
    };
    if (seat) {
      p.pos.copy(seat.position);
      p.yaw = seat.yaw;
      p.drop = (seat.height ?? 0.47) - HIP_Y * p.scale; // lower the body so the hips rest on the seat
    } else {
      p.local = Math.random() < localShare;
      p.from = pick(p.local ? localNodes : nodeNames);
      p.to = pick(nextOptions(p, p.from, null));
      p.pos.lerpVectors(nodePos[p.from], nodePos[p.to], Math.random());
      if (Math.random() < 0.2) p.wait = rand(0, 6);
    }
    people.push(p);

    const skin = new THREE.Color(pick(SKIN)), shirt = new THREE.Color(pick(SHIRTS)), pants = new THREE.Color(pick(PANTS));
    heads.setColorAt(i, skin);
    torsos.setColorAt(i, shirt);
    arms.setColorAt(2 * i, shirt); arms.setColorAt(2 * i + 1, shirt);
    legs.setColorAt(2 * i, pants); legs.setColorAt(2 * i + 1, pants);
  }
  for (const m of [heads, torsos, arms, legs]) m.instanceColor.needsUpdate = true;

  // ---- per-frame
  const base = new THREE.Matrix4(), part = new THREE.Matrix4(), rot = new THREE.Matrix4(), out = new THREE.Matrix4();
  const q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), scl = new THREE.Vector3();
  const target = new THREE.Vector3(), dir = new THREE.Vector3(), side = new THREE.Vector3();

  function setPart(mesh, index, x, y, z, swingX) {
    part.makeTranslation(x, y, z);
    rot.makeRotationX(swingX);
    out.multiplyMatrices(base, part).multiply(rot);
    mesh.setMatrixAt(index, out);
  }

  // A summoned visitor walks straight to their spot, then waits there facing `lookAt`.
  function approach(p, dt) {
    const s = p.summon;
    dir.subVectors(s.point, p.pos).setY(0);
    const dist = dir.length();
    if (s.arrived || dist < 0.15) {
      s.arrived = true;
      turnTo(p, Math.atan2(s.lookAt.x - p.pos.x, s.lookAt.z - p.pos.z), dt);
      return false;
    }
    dir.divideScalar(dist);
    p.pos.addScaledVector(dir, Math.min(dist, Math.max(p.speed, VISIT_SPEED) * dt));
    turnTo(p, Math.atan2(dir.x, dir.z), dt);
    return true;
  }

  function turnTo(p, want, dt) {
    let d = want - p.yaw;
    d = Math.atan2(Math.sin(d), Math.cos(d));
    p.yaw += d * Math.min(1, dt * 4);
  }

  function steer(p, dt) {
    if (p.talking) { if (p.faceYaw !== null) turnTo(p, p.faceYaw, dt); return false; }
    if (p.summon) return approach(p, dt);
    if (p.wait > 0) { p.wait -= dt; return false; }
    // aim at the next node, shifted sideways so people don't walk single file
    const a = nodePos[p.from], b = nodePos[p.to];
    dir.subVectors(b, a).setY(0).normalize();
    side.set(-dir.z, 0, dir.x);
    target.copy(b).addScaledVector(side, p.offset);
    dir.subVectors(target, p.pos).setY(0);
    const dist = dir.length();
    if (dist < 0.3) {
      const next = pick(nextOptions(p, p.to, p.from));
      p.from = p.to;
      p.to = next;
      if (Math.random() < 0.3) p.wait = rand(2, 7); // pause at junctions now and then
      return false;
    }
    if (Math.random() < dt * 0.02) p.wait = rand(1.5, 4); // the odd mid-path stop
    dir.divideScalar(dist);
    p.pos.addScaledVector(dir, Math.min(dist, p.speed * dt));
    turnTo(p, Math.atan2(dir.x, dir.z), dt);
    return true;
  }

  function update(dt) {
    for (let i = 0; i < count; i++) {
      const p = people[i];
      let legSwing, armSwing, drop = 0;
      if (p.seated) {
        legSwing = [SEATED_LEGS, SEATED_LEGS];
        armSwing = [SEATED_ARMS, SEATED_ARMS];
        drop = p.drop / p.scale; // parts are placed in the person's scaled space
      } else {
        const moving = steer(p, dt);
        p.swing += ((moving ? 1 : 0) - p.swing) * Math.min(1, dt * 5);
        if (moving) p.phase += dt * p.speed * 5.5;
        const s = Math.sin(p.phase) * 0.45 * p.swing;
        legSwing = [s, -s];
        armSwing = [-s * 0.8, s * 0.8];
      }
      q.setFromAxisAngle(up, p.yaw);
      base.compose(p.pos, q, scl.setScalar(p.scale));
      setPart(torsos, i, 0, 1.15 + drop, 0, 0);
      setPart(heads, i, 0, 1.6 + drop, 0, 0);
      setPart(legs, 2 * i, -LEG_X, HIP_Y + drop, 0, legSwing[0]);
      setPart(legs, 2 * i + 1, LEG_X, HIP_Y + drop, 0, legSwing[1]);
      setPart(arms, 2 * i, -ARM_X, SHOULDER_Y + drop, 0, armSwing[0]);
      setPart(arms, 2 * i + 1, ARM_X, SHOULDER_Y + drop, 0, armSwing[1]);
    }
    for (const m of [heads, torsos, arms, legs]) m.instanceMatrix.needsUpdate = true;
  }

  // ---- talking API (used by main.js)
  // nearest person within `range` meters (horizontally) of `pos`, or -1. Seated
  // people count from the edge of their chair, `seatedExtra` meters further out.
  function nearest(pos, range, seatedExtra = 0) {
    let best = -1, bestD = range;
    for (let i = 0; i < count; i++) {
      const p = people[i];
      const d = Math.hypot(p.pos.x - pos.x, p.pos.z - pos.z) - (p.seated ? seatedExtra : 0);
      if (d < bestD) { best = i; bestD = d; }
    }
    return best;
  }
  // top of the person's head (seated people sit lower)
  function headTop(i, out = new THREE.Vector3()) {
    const p = people[i];
    return out.set(p.pos.x, p.scale * 1.73 + (p.seated ? p.drop : 0), p.pos.z);
  }
  // stop and (if standing) turn to face `towards`; seated people stay facing their table
  function startTalk(i, towards) {
    const p = people[i];
    p.talking = true;
    p.faceYaw = p.seated ? null : Math.atan2(towards.x - p.pos.x, towards.z - p.pos.z);
  }
  function endTalk(i) {
    const p = people[i];
    p.talking = false;
    p.wait = rand(0.5, 2); // a beat before walking off again
  }

  // ---- visitors (used by seating.js)
  // closest walker who is free to come over (not seated, talking or already visiting)
  function pickVisitor(pos, maxDist = 80) {
    let best = -1, bestD = maxDist;
    for (let i = 0; i < count; i++) {
      const p = people[i];
      if (p.seated || p.talking || p.summon || p.visitedAt > performance.now() - REVISIT_MS) continue;
      const d = Math.hypot(p.pos.x - pos.x, p.pos.z - pos.z);
      if (d < bestD) { best = i; bestD = d; }
    }
    return best;
  }
  function summon(i, point, lookAt) {
    people[i].summon = { point: point.clone(), lookAt: lookAt.clone(), arrived: false };
  }
  const hasArrived = (i) => !!people[i].summon?.arrived;
  // let a visitor go: rejoin the path network at the nearest node and walk off
  function dismiss(i) {
    const p = people[i];
    p.summon = null;
    p.visitedAt = performance.now(); // someone else comes next time
    let near = null, nearD = Infinity;
    for (const n of p.local ? localNodes : nodeNames) {
      const d = nodePos[n].distanceTo(p.pos);
      if (d < nearD) { near = n; nearD = d; }
    }
    p.to = near;
    p.from = pick(neighbors[near]);
  }

  update(0);
  return {
    update, count, nearest, headTop, startTalk, endTalk, pickVisitor, summon, hasArrived, dismiss,
    position: (i) => people[i].pos,
    isSeated: (i) => people[i].seated,
  };
}
