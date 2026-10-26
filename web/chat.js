// Talking to people. When the tree gets close to someone (walking or seated), a
// "Press Space Bar to talk" bubble pops up over their head. Space starts a chat:
// the person stops, the camera swings to an over-the-shoulder view from behind
// the tree, and a speech bubble shows the next blast email (emails.json), styled
// like an email: sender, subject, then the message.
// Space again ends the chat and the camera swings back.

import * as THREE from "three";

// The tree's widest branches reach ~0.55 m from its center; a person "is within
// half a person's height" (0.85 m) when the gap between them is that small.
const TREE_RADIUS = 0.55;
const TALK_GAP = 0.85;
const TALK_RANGE = TREE_RADIUS + TALK_GAP;
// Seated people are boxed in by their (1.5x size) chair and table, so their
// range is measured from the outside of the chair rather than their body.
const SEATED_EXTRA = 0.75;

// Over-the-shoulder camera, relative to the tree and the direction to the person
// lookLift aims a little above the person's head, so they sit in the lower part
// of the screen and the email has room above them.
const SHOULDER = { back: 1.9, right: 0.6, up: 1.75, lookLift: 0.5 };
const EMAILS_URL = "emails.json"; // made from gsb_blast_emails.csv by make_dialogue.py
const EASE = 6; // camera follow sharpness (higher = snappier)

// ---------------------------------------------------------------- random lines
const OPENERS = [
  "Oh, hi!", "Hey there!", "Well hello, little tree.", "Whoa, a walking tree?", "Hi! Love the needles.",
  "Oh! I didn't see you there.", "Hey, are you new to the GSB?", "Good afternoon!",
];
const WALKING = [
  "I just got out of accounting and my brain is fried.",
  "I'm heading to a case discussion in McClelland.",
  "The line at Arbuckle was so long today.",
  "Have you seen the view from the top of the Bass Center?",
  "Town Square is so sunny this afternoon.",
  "I'm looking for a quiet spot to study before my next class.",
  "Someone said there's free coffee in the CEMEX Auditorium.",
  "I'm supposed to be networking, but everyone's at lunch.",
  "I think I'm lost. Which way is Zambrano Hall?",
  "My study group meets in Patterson in ten minutes.",
];
const SEATED = [
  "This table has the best shade on campus.",
  "I've been sitting here since my 9 a.m. class.",
  "The pergola makes the coolest striped shadows, right?",
  "Pull up a chair! Well... if you can sit.",
  "I'm pretending to read this case, but mostly people-watching.",
  "Arbuckle's lunch special is actually pretty good today.",
];
const CLOSERS = [
  "Anyway, good luck out there!", "Want to grab a coffee sometime?", "Try not to shed on the chairs.",
  "See you around campus!", "Watch out for the squirrels.", "Catch you at the next mixer!",
  "Don't let anyone hang ornaments on you.", "Have a great rest of your day!",
];
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const randomLine = (seated) => `${pick(OPENERS)} ${pick(seated ? SEATED : WALKING)} ${pick(CLOSERS)}`;

// ---------------------------------------------------------------- emails
// Each conversation shows the next email from emails.json, top to bottom,
// starting over after the last one. If the file can't be loaded, people fall
// back to the random lines above.
let emails = null;
fetch(EMAILS_URL)
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
  .then((list) => { emails = list.length ? list : null; })
  .catch((err) => console.warn(`GSB: no ${EMAILS_URL} (${err.message}); using random lines`));
let nextEmail = 0;

const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// plain-text email body -> HTML: *bold* and [link] / [image] markers
function bodyHtml(text) {
  return escapeHtml(text)
    .replace(/\*([^*\n]+)\*/g, "<strong>$1</strong>")
    .replace(/\[(link|image)\]/g, '<span class="tag">$1</span>');
}

function emailHtml(m) {
  const attach = m.attachments?.length
    ? `<div class="attach">📎 ${m.attachments.map(escapeHtml).join(" · ")}</div>` : "";
  return `
    <div class="mail-head">
      <span class="from"><strong>${escapeHtml(m.sender)}</strong> <span class="addr">&lt;${escapeHtml(m.email)}&gt;</span></span>
      <span class="date">${escapeHtml(m.date)}</span>
    </div>
    <div class="subject">${escapeHtml(m.subject)}</div>
    <div class="mail-body">${bodyHtml(m.body)}</div>
    ${attach}`;
}

function nextMessageHtml(seated) {
  if (!emails) return `<div class="mail-body">${escapeHtml(randomLine(seated))}</div>`;
  const m = emails[nextEmail];
  nextEmail = (nextEmail + 1) % emails.length;
  return emailHtml(m);
}

// ---------------------------------------------------------------- bubbles
export function makeBubble(className, html) {
  const el = document.createElement("div");
  el.className = `bubble ${className}`;
  el.innerHTML = html;
  el.hidden = true;
  document.body.appendChild(el);
  return el;
}

// Show `el` with its tail just above the world point `at`, kept fully on screen.
const screen = new THREE.Vector3();
export function placeBubble(el, at, camera) {
  screen.copy(at).project(camera);
  if (screen.z > 1) { el.hidden = true; return; } // behind the camera
  el.hidden = false;
  const half = el.offsetWidth / 2 + 8;
  const x = ((screen.x + 1) / 2) * window.innerWidth;
  const y = ((1 - screen.y) / 2) * window.innerHeight;
  el.style.left = `${Math.min(Math.max(x, half), window.innerWidth - half)}px`;
  el.style.top = `${Math.max(y, el.offsetHeight + 20)}px`;
}

export function createChat({ camera, controls, player, people }) {
  const prompt = makeBubble("prompt", "Press <kbd>Space Bar</kbd> to talk");
  const chatBox = makeBubble("chat", `<div class="message"></div><p class="exit">Press <kbd>Space Bar</kbd> again to exit chat.</p>`);
  const messageEl = chatBox.querySelector(".message");

  // long emails scroll: mouse wheel over the box, or arrow / page keys during a chat
  window.addEventListener("keydown", (e) => {
    if (chat?.phase !== "in") return;
    const body = messageEl.querySelector(".mail-body");
    const step = { ArrowDown: 60, ArrowUp: -60, PageDown: 240, PageUp: -240 }[e.code];
    if (body && step) { body.scrollTop += step; e.preventDefault(); }
  });

  let near = -1;      // person who would answer if Space were pressed now
  let offered = -1;   // a visitor seating.js has brought over (overrides proximity)
  let autoDetect = true;
  let onEnd = null;
  let chat = null;    // { index, phase: "in" | "out", saved, savedDir, lookDist, pos, target, restore }
  const head = new THREE.Vector3();
  const dir = new THREE.Vector3(), side = new THREE.Vector3();
  const wantPos = new THREE.Vector3(), wantTarget = new THREE.Vector3();

  function placeAbove(el, i, lift) {
    people.headTop(i, head);
    head.y += lift;
    placeBubble(el, head, camera);
  }

  function begin(i) {
    const tree = player.object.position;
    chat = {
      index: i,
      phase: "in",
      // the view to come back to, relative to the tree
      saved: camera.position.clone().sub(tree),
      savedDir: camera.getWorldDirection(new THREE.Vector3()),
      lookDist: controls.enabled ? camera.position.distanceTo(controls.target) : 6,
      pos: camera.position.clone(),
      target: camera.position.clone().addScaledVector(camera.getWorldDirection(new THREE.Vector3()), 6),
      restore: { controls: controls.enabled, player: player.isEnabled() },
    };
    controls.enabled = false;
    player.setEnabled(false);
    player.faceTowards(people.position(i));
    people.startTalk(i, tree);
    messageEl.innerHTML = nextMessageHtml(people.isSeated(i));
    messageEl.querySelector(".mail-body").scrollTop = 0;
    prompt.hidden = true;
  }

  function end() {
    people.endTalk(chat.index);
    chatBox.hidden = true;
    chat.phase = "out";
    const i = chat.index;
    if (i === offered) offered = -1;
    onEnd?.(i);
  }

  // Space: end a chat, or start one with whoever is prompting. Returns true if used.
  function handleSpace() {
    if (chat?.phase === "in") { end(); return true; }
    if (!chat && near >= 0) { begin(near); return true; }
    return false;
  }

  function update(dt) {
    const tree = player.object.position;
    const k = 1 - Math.exp(-EASE * dt);

    if (chat) {
      if (chat.phase === "in") {
        // behind the tree's right shoulder, looking at the person's face
        const pp = people.position(chat.index);
        dir.set(pp.x - tree.x, 0, pp.z - tree.z).normalize();
        side.set(-dir.z, 0, dir.x);
        wantPos.set(tree.x, 0, tree.z).addScaledVector(dir, -SHOULDER.back).addScaledVector(side, SHOULDER.right);
        wantPos.y = tree.y + SHOULDER.up; // tree.y is raised when it sits on a chair
        people.headTop(chat.index, wantTarget);
        wantTarget.y += SHOULDER.lookLift;
      } else {
        // back to the view from before the chat
        wantPos.copy(tree).add(chat.saved);
        wantTarget.copy(wantPos).addScaledVector(chat.savedDir, chat.lookDist);
      }
      chat.pos.lerp(wantPos, k);
      chat.target.lerp(wantTarget, k);
      camera.position.copy(chat.pos);
      camera.lookAt(chat.target);

      if (chat.phase === "in") {
        placeAbove(chatBox, chat.index, 0.25);
      } else if (chat.pos.distanceTo(wantPos) < 0.05 && chat.target.distanceTo(wantTarget) < 0.05) {
        camera.position.copy(wantPos);
        camera.lookAt(wantTarget);
        if (chat.restore.controls) controls.target.copy(wantTarget);
        controls.enabled = chat.restore.controls;
        player.setEnabled(chat.restore.player);
        chat = null;
      }
      return;
    }

    near = offered >= 0 ? offered : autoDetect ? people.nearest(tree, TALK_RANGE, SEATED_EXTRA) : -1;
    if (near >= 0) placeAbove(prompt, near, 0.25);
    else prompt.hidden = true;
  }

  return {
    update,
    handleSpace,
    isChatting: () => chat !== null,
    hasCandidate: () => near >= 0,
    // seating.js: offer a specific person to talk to, and turn proximity prompts off/on
    offer(i) { offered = i; },
    clearOffer() { offered = -1; },
    setAutoDetect(on) { autoDetect = on; },
    set onEnd(fn) { onEnd = fn; },
  };
}
