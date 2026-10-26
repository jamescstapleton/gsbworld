// Sitting at the Arbuckle tables. Near a table nobody is using, a "Press Space Bar
// to sit down" bubble appears over the closest chair. Sitting puts the camera
// over the tree's shoulder, looking across the table. Then visitors come by one
// at a time: a walker comes over to stand across the table, the usual talk
// prompt appears, and after the chat they walk off. The next visitor sets out
// 5 seconds later. Any movement key stands the tree back up.

import * as THREE from "three";
import { makeBubble, placeBubble } from "./chat.js";

const SIT_RANGE = 2.8;        // m from a table's center at which the tree can sit
const FIRST_VISIT = 1.5;      // s after sitting before the first visitor sets out
const NEXT_VISIT = 5;         // s after a chat ends before the next visitor sets out
const RETRY = 2;              // s to wait if nobody is free to come over
const VISITOR_SPOT = 2.3;     // m from the table center, on the far side from the tree
const STAND_BACK = 1.15;      // m behind the chair where the tree stands up
const SEAT_VIEW = { back: 1.7, right: 0.5, up: 2.0, look: 1.4, lookHeight: 1.3 };
const EASE = 6;

export function createSeating({ camera, controls, player, people, chat, tables, seatHeight, hint }) {
  const sitPrompt = makeBubble("prompt", "Press <kbd>Space Bar</kbd> to sit down");
  const walkHint = hint.textContent;

  let candidate = null;   // free chair the tree could sit in right now
  let seat = null;        // { chair, saved: camera offset to return to, cam: { pos, target } }
  let returning = null;   // camera easing back after standing: { pos, target, saved, savedTarget }
  let visit = null;       // { state: "waiting" | "coming" | "here", timer, index }
  const at = new THREE.Vector3(), tmp = new THREE.Vector3();
  const wantPos = new THREE.Vector3(), wantTarget = new THREE.Vector3();

  const isEmpty = (table) => table.chairs.every((c) => !c.occupied);

  function findCandidate() {
    const tree = player.object.position;
    let best = null, bestD = SIT_RANGE;
    for (const t of tables) {
      const d = Math.hypot(t.pos.x - tree.x, t.pos.z - tree.z);
      if (d < bestD && isEmpty(t)) { best = t; bestD = d; }
    }
    if (!best) return null;
    let chair = null, chairD = Infinity; // the chair nearest the tree
    for (const c of best.chairs) {
      const d = Math.hypot(c.pos.x - tree.x, c.pos.z - tree.z);
      if (d < chairD) { chair = c; chairD = d; }
    }
    return chair;
  }

  function sit(chair) {
    const tree = player.object.position;
    const look = controls.target.clone();
    seat = {
      chair,
      saved: camera.position.clone().sub(tree),     // walking view, relative to the tree
      savedTarget: look.sub(tree),
      cam: { pos: camera.position.clone(), target: controls.target.clone() },
    };
    chair.occupied = true;
    controls.enabled = false;
    player.sit(chair.seat, chair.yaw, seatHeight);
    chat.setAutoDetect(false);
    sitPrompt.hidden = true;
    visit = { state: "waiting", timer: FIRST_VISIT, index: -1 };
    hint.textContent = "Sitting · visitors will come by · Space to talk · WASD / arrows to stand up";
  }

  function stand() {
    if (visit?.index >= 0) { chat.clearOffer(); people.dismiss(visit.index); }
    visit = null;
    const { chair } = seat;
    chair.occupied = false;
    player.stand(tmp.copy(chair.pos).addScaledVector(chair.toTable, -STAND_BACK));
    chat.setAutoDetect(true);
    const tree = player.object.position;
    returning = {
      pos: seat.cam.pos.clone(), target: seat.cam.target.clone(),
      wantPos: tree.clone().add(seat.saved), wantTarget: tree.clone().add(seat.savedTarget),
    };
    seat = null;
    hint.textContent = walkHint;
  }
  player.onStandRequest = () => { if (seat && !chat.isChatting()) stand(); };

  chat.onEnd = (i) => {
    if (visit && i === visit.index) {
      people.dismiss(i);              // they walk off after the chat
      visit = { state: "waiting", timer: NEXT_VISIT, index: -1 };
    }
  };

  function runVisits(dt) {
    const tree = player.object.position;
    if (visit.state === "waiting") {
      visit.timer -= dt;
      if (visit.timer > 0) return;
      const i = people.pickVisitor(tree);
      if (i < 0) { visit.timer = RETRY; return; }
      // stand across the table from the tree, facing it
      const { chair } = seat;
      tmp.copy(chair.table.pos).addScaledVector(chair.toTable, VISITOR_SPOT).setY(0);
      people.summon(i, tmp, tree);
      visit = { state: "coming", timer: 0, index: i };
    } else if (visit.state === "coming" && people.hasArrived(visit.index)) {
      chat.offer(visit.index);        // shows the usual "Press Space Bar to talk"
      visit.state = "here";
    }
  }

  function seatedCamera(dt) {
    const k = 1 - Math.exp(-EASE * dt);
    const tree = player.object.position, { chair } = seat;
    const d = chair.toTable, side = tmp.set(-d.z, 0, d.x);
    wantPos.set(tree.x, tree.y + SEAT_VIEW.up, tree.z)
      .addScaledVector(d, -SEAT_VIEW.back).addScaledVector(side, SEAT_VIEW.right);
    wantTarget.copy(chair.table.pos).addScaledVector(d, SEAT_VIEW.look).setY(SEAT_VIEW.lookHeight);
    seat.cam.pos.lerp(wantPos, k);
    seat.cam.target.lerp(wantTarget, k);
    camera.position.copy(seat.cam.pos);
    camera.lookAt(seat.cam.target);
  }

  function update(dt) {
    if (seat) {
      if (!chat.isChatting()) seatedCamera(dt);
      else seat.cam.pos.copy(camera.position); // pick up smoothly from wherever the chat leaves it
      runVisits(dt);
      return;
    }
    if (returning) {
      const k = 1 - Math.exp(-EASE * dt);
      returning.pos.lerp(returning.wantPos, k);
      returning.target.lerp(returning.wantTarget, k);
      camera.position.copy(returning.pos);
      camera.lookAt(returning.target);
      if (returning.pos.distanceTo(returning.wantPos) < 0.05) {
        camera.position.copy(returning.wantPos);
        controls.target.copy(returning.wantTarget);
        controls.enabled = true;
        returning = null;
      }
      return;
    }
    // walking: offer a seat at an empty table, unless someone is there to talk to
    candidate = chat.isChatting() || chat.hasCandidate() ? null : findCandidate();
    if (candidate) placeBubble(sitPrompt, at.copy(candidate.pos).setY(1.9), camera);
    else sitPrompt.hidden = true;
  }

  // Space: sit down if a seat is on offer. Returns true if used.
  function handleSpace() {
    if (candidate && !seat && !returning) { sit(candidate); candidate = null; return true; }
    return false;
  }

  return { update, handleSpace, isSeated: () => !!seat };
}
