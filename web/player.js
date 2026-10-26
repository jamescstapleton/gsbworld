// The player: a plain low-poly Christmas tree (no star or ornaments) with legs, the same height as the
// people (1.7 m), with only the bottom third of its legs showing below the
// branches. WASD walks relative to the camera, arrow keys move 3x faster, Shift
// doubles either. The orbit
// camera follows along, so you can still drag to look around. Walls, posts,
// tables and trunks block movement (horizontal ray tests at knee and waist height).

import * as THREE from "three";

const PEOPLE_SPEED = 0.6;        // average stroll of the crowd (people.js: 0.4-0.8 m/s)
const WALK = 5 * PEOPLE_SPEED;   // m/s: five times the crowd
const RUN = 2 * WALK;            // with Shift
const ARROW_BOOST = 3;           // arrow keys cover ground 3x faster than WASD
// Camera swings behind the tree's heading while walking: 1 - e^(-1.5 * 2 s) = 95%
// of a turn is caught up after about 2 seconds.
const FOLLOW_RATE = 1.5;
const RADIUS = 0.45;             // how close the tree can get to things (lets it squeeze between chairs)
const PROBE_HEIGHTS = [0.3, 1.0];

const HEIGHT = 1.7;              // tip of the top tier
const HIP_Y = 0.45, LEG_LEN = 0.45;
const SEATED_LEGS = -1.35; // legs stuck out forward when sitting
const SKIRT_Y = HIP_Y - LEG_LEN * (2 / 3); // lowest branches: bottom 1/3 of the legs shows

function buildTree(patchMaterial) {
  const mat = (color, extra = {}) => {
    const m = new THREE.MeshStandardMaterial({ color, roughness: 0.8, flatShading: true, ...extra });
    patchMaterial?.(m);
    return m;
  };
  const needles = mat(0x1f6b35), bark = mat(0x5a3b22), white = mat(0xffffff), black = mat(0x111111);
  const tree = new THREE.Group();

  // three stacked tiers, widest at the bottom, sitting on the leg "skirt";
  // the top tier comes to a point at HEIGHT
  const tiers = [
    { r: 0.55, bottom: SKIRT_Y, h: 0.65 },
    { r: 0.44, bottom: 0.62, h: 0.55 },
    { r: 0.31, bottom: 1.0, h: HEIGHT - 1.0 },
  ];
  for (const t of tiers) {
    const cone = new THREE.Mesh(new THREE.ConeGeometry(t.r, t.h, 8), needles);
    cone.position.y = t.bottom + t.h / 2;
    tree.add(cone);
  }

  // radius of the outermost tier at height y, for sticking things onto the surface
  const surfaceR = (y) => Math.max(0, ...tiers.filter((t) => y >= t.bottom && y <= t.bottom + t.h)
    .map((t) => t.r * (1 - (y - t.bottom) / t.h)));

  for (const sx of [-1, 1]) { // eyes on the front (+Z) of the middle tier
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.07, 8, 6), white);
    eye.position.set(0.1 * sx, 0.86, surfaceR(0.86) + 0.01);
    const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.035, 6, 4), black);
    pupil.position.set(0, 0, 0.05);
    eye.add(pupil);
    tree.add(eye);
  }

  const legs = [];
  for (const sx of [-1, 1]) {
    const hip = new THREE.Group(); // pivot inside the bottom tier
    hip.position.set(0.11 * sx, HIP_Y, 0);
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.09, LEG_LEN, 0.1), bark);
    leg.position.y = -LEG_LEN / 2;
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.06, 0.2), bark);
    foot.position.set(0, -LEG_LEN + 0.03, 0.05);
    hip.add(leg, foot);
    tree.add(hip);
    legs.push(hip);
  }
  tree.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  return { tree, legs };
}

export function createPlayer(scene, { start, facing = 0, camera, controls, collidables, patchMaterial }) {
  const { tree, legs } = buildTree(patchMaterial);
  tree.position.copy(start);
  tree.rotation.y = facing;
  scene.add(tree);

  // camera starts behind and above the tree
  const behind = new THREE.Vector3(Math.sin(facing), 0, Math.cos(facing)).multiplyScalar(-7);
  camera.position.copy(start).add(behind).add(new THREE.Vector3(0, 3.5, 0));
  controls.target.copy(start).add(new THREE.Vector3(0, 1.1, 0));
  controls.update();

  const keys = new Set();
  window.addEventListener("keydown", (e) => {
    keys.add(e.code);
    if (e.code.startsWith("Arrow") || e.code === "Space") e.preventDefault();
  });
  window.addEventListener("keyup", (e) => keys.delete(e.code));
  window.addEventListener("blur", () => keys.clear());

  const ray = new THREE.Raycaster();
  const origin = new THREE.Vector3(), forward = new THREE.Vector3(), right = new THREE.Vector3();
  const move = new THREE.Vector3(), step = new THREE.Vector3(), before = new THREE.Vector3();
  let phase = 0, swing = 0;

  function blocked(dx, dz) {
    const len = Math.hypot(dx, dz);
    if (len === 0) return false;
    step.set(dx / len, 0, dz / len);
    ray.far = len + RADIUS;
    for (const h of PROBE_HEIGHTS) {
      origin.set(tree.position.x, h, tree.position.z);
      ray.set(origin, step);
      if (ray.intersectObjects(collidables, false).length) return true;
    }
    return false;
  }

  let enabled = true, faceYaw = null;

  // camera follow: don't fight the player while they're dragging the view
  let dragging = false;
  controls.addEventListener("start", () => { dragging = true; });
  controls.addEventListener("end", () => { dragging = false; });
  const offset = new THREE.Vector3(), orbit = new THREE.Spherical();
  const moveRef = new THREE.Vector3(0, 0, -1);
  let lastCombo = "0,0";

  function turnTo(want, dt) {
    let d = want - tree.rotation.y;
    d = Math.atan2(Math.sin(d), Math.cos(d));
    tree.rotation.y += d * Math.min(1, dt * 10);
  }

  let seated = false, onStandRequest = null;

  function update(dt) {
    const held = (...codes) => enabled && codes.some((c) => keys.has(c));
    const fwd = (held("KeyW", "ArrowUp") ? 1 : 0) - (held("KeyS", "ArrowDown") ? 1 : 0);
    const str = (held("KeyD", "ArrowRight") ? 1 : 0) - (held("KeyA", "ArrowLeft") ? 1 : 0);

    if (seated) {
      // legs out in front; any movement key asks to stand up (seating.js decides)
      legs[0].rotation.x = legs[1].rotation.x = SEATED_LEGS;
      if ((fwd || str) && onStandRequest) onStandRequest();
      lastCombo = "seated";
      return;
    }

    // Directions are relative to the camera as it was when the current key combo
    // started (or while the view is being dragged). Reading the live camera every
    // frame would chase its own tail now that the camera follows the tree: holding
    // a side key would turn the tree, swing the camera, turn the tree again...
    const combo = `${fwd},${str}`;
    if (combo !== lastCombo || dragging) {
      camera.getWorldDirection(moveRef).setY(0).normalize();
      lastCombo = combo;
    }
    forward.copy(moveRef);
    right.set(-forward.z, 0, forward.x);
    move.set(0, 0, 0).addScaledVector(forward, fwd).addScaledVector(right, str);

    before.copy(tree.position);
    const moving = move.lengthSq() > 0;
    if (moving) {
      let speed = held("ShiftLeft", "ShiftRight") ? RUN : WALK;
      if (held("ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight")) speed *= ARROW_BOOST;
      move.normalize().multiplyScalar(speed * dt);
      // try the full step, then slide along walls on one axis
      if (!blocked(move.x, move.z)) tree.position.add(move);
      else if (!blocked(move.x, 0)) tree.position.x += move.x;
      else if (!blocked(0, move.z)) tree.position.z += move.z;

      turnTo(Math.atan2(move.x, move.z), dt);
      phase += dt * Math.min(speed, 5) * 7; // quick little steps (capped so sprints don't blur)
    } else if (faceYaw !== null) {
      turnTo(faceYaw, dt);
    }
    swing += ((moving ? 1 : 0) - swing) * Math.min(1, dt * 8);
    const s = Math.sin(phase) * 0.6 * swing;
    legs[0].rotation.x = s;
    legs[1].rotation.x = -s;
    tree.position.y = Math.abs(Math.sin(phase)) * 0.04 * swing; // little bounce

    // carry the camera along with the tree
    step.subVectors(tree.position, before).setY(0);
    camera.position.add(step);
    controls.target.add(step);

    // while walking, swing the camera around behind the tree's heading, gradually
    // (keeps the player's chosen distance and height; paused while they drag the view)
    if (moving && !dragging) {
      offset.subVectors(camera.position, controls.target);
      orbit.setFromVector3(offset);
      let d = tree.rotation.y + Math.PI - orbit.theta; // "behind" = opposite the facing
      d = Math.atan2(Math.sin(d), Math.cos(d));
      orbit.theta += d * (1 - Math.exp(-FOLLOW_RATE * dt));
      offset.setFromSpherical(orbit);
      camera.position.copy(controls.target).add(offset);
    }
  }

  return {
    object: tree,
    update,
    // movement keys are ignored while disabled (e.g. during a chat)
    setEnabled(on) { enabled = on; if (on) faceYaw = null; },
    isEnabled: () => enabled,
    // turn (while standing) to face a world point
    faceTowards(point) { if (!seated) faceYaw = Math.atan2(point.x - tree.position.x, point.z - tree.position.z); },
    // sit with hips at seatHeight, feet at `position`, facing `yaw`
    sit(position, yaw, seatHeight) {
      seated = true;
      faceYaw = null;
      swing = 0;
      tree.position.set(position.x, seatHeight - HIP_Y, position.z);
      tree.rotation.y = yaw;
    },
    stand(position) {
      seated = false;
      legs[0].rotation.x = legs[1].rotation.x = 0;
      tree.position.set(position.x, 0, position.z);
    },
    isSeated: () => seated,
    set onStandRequest(fn) { onStandRequest = fn; },
  };
}
