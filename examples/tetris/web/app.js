import { Game, HEIGHT, HIDDEN, SHAPES, WIDTH, cellsOf, dropped, frontier, heights, labels } from "./tetris.js";

// Same piece colours as the images OpenJev sees (vision.py).
const COLORS = { I: "#00c8dc", O: "#f0c800", T: "#a555e1", S: "#46c35a", Z: "#e6414b", J: "#3273f0", L: "#f58c1e" };
const PACE = { key: 70, lock: 50, flash: 170, collapse: 150, answer: 330, settle: 140, forced: 280 };
const GOAL = 10;
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ small helpers

function parseColor(color) {
  if (color.startsWith("#")) {
    const n = parseInt(color.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  return color.match(/\d+/g).slice(0, 3).map(Number);
}
function mix(a, b, t) {
  const [x, y] = [parseColor(a), parseColor(b)];
  const c = x.map((v, i) => Math.round(v + (y[i] - v) * Math.max(0, Math.min(1, t))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
const easeOut = (t) => 1 - (1 - Math.max(0, Math.min(1, t))) ** 3;
const easeIn = (t) => Math.max(0, Math.min(1, t)) ** 2;

function setupCanvas(canvas, width, height) {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return ctx;
}

function block(ctx, x, y, size, color, lift = 0) {
  const rim = Math.max(1, Math.floor(size / 14));
  ctx.fillStyle = mix(color, "#000000", 0.42);
  ctx.fillRect(x, y, size, size);
  const face = lift ? mix(color, "#ffffff", lift) : color;
  ctx.fillStyle = face;
  ctx.fillRect(x + rim, y + rim, size - 2 * rim, size - 2 * rim);
  ctx.fillStyle = mix(face, "#ffffff", 0.18);
  ctx.fillRect(x + rim, y + rim, size - 2 * rim, Math.max(1, Math.floor(size / 9)));
}

class Cancelled extends Error {}
let session = 0;
let speed = 1;
function wait(ms, token) {
  return new Promise((resolve, reject) => {
    setTimeout(() => (token === session ? resolve() : reject(new Cancelled())), ms / speed);
  });
}
function check(token) {
  if (token !== session) throw new Cancelled();
}
async function animate(ms, token, step) {
  const start = performance.now();
  const duration = ms / speed;
  for (;;) {
    check(token);
    const t = duration <= 0 ? 1 : (performance.now() - start) / duration;
    step(Math.min(1, t));
    if (t >= 1) return;
    await new Promise((r) => requestAnimationFrame(r));
  }
}

// ------------------------------------------------------------------ rendering

const view = {
  game: null,
  drop: null, // {piece, from, y}: an animated copy of the falling piece
  flash: null, // {board, rows, t}
  collapse: null, // {board, rows, t}
  hidePiece: false,
};

const wellCanvas = $("well");
const nextCanvas = $("next");
let wellCtx, nextCtx, cell;

function sizeCanvases() {
  // 28 px cells on desktop; on narrow screens the well shrinks to fit (frame padding 2 x 13 px).
  const room = Math.min(window.innerWidth, document.documentElement.clientWidth) - 32 - 26;
  cell = Math.max(16, Math.min(28, Math.floor(room / WIDTH)));
  wellCtx = setupCanvas(wellCanvas, cell * WIDTH, cell * HEIGHT);
  nextCtx = setupCanvas(nextCanvas, 110, 150);
}

function drawWell() {
  const ctx = wellCtx;
  const w = cell * WIDTH, h = cell * HEIGHT;
  ctx.fillStyle = "#0b110d";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#141d17";
  for (let c = 1; c < WIDTH; c++) ctx.fillRect(c * cell, 0, 1, h);
  for (let r = 1; r < HEIGHT; r++) ctx.fillRect(0, r * cell, w, 1);
  const game = view.game;
  if (!game) return;
  let board = game.board;
  const offsets = new Map();
  if (view.collapse) {
    board = view.collapse.board;
    const shift = easeOut(view.collapse.t);
    board.forEach((_, y) => {
      if (view.collapse.rows.includes(y)) offsets.set(y, null);
      else offsets.set(y, view.collapse.rows.filter((f) => f > y).length * shift);
    });
  } else if (view.flash) {
    board = view.flash.board;
  }
  for (let y = HIDDEN; y < HIDDEN + HEIGHT; y++) {
    if (view.collapse && offsets.get(y) === null) continue;
    const dy = offsets.get(y) || 0;
    let lift = 0;
    if (view.flash && view.flash.rows.includes(y)) lift = 0.85 * Math.sin(Math.PI * view.flash.t);
    board[y].forEach((kind, x) => {
      if (kind) block(ctx, x * cell, (y - HIDDEN + dy) * cell, cell, COLORS[kind], lift);
    });
  }
  const piece = view.drop ? view.drop.piece : game.piece;
  if (piece && !view.hidePiece && !game.over) {
    const dy = view.drop ? view.drop.y - piece.y : 0;
    if (view.drop) {
      const tops = new Map();
      for (const [x, y] of cellsOf(piece)) tops.set(x, Math.min(tops.get(x) ?? y, y));
      const length = Math.min(4, view.drop.y - view.drop.from);
      for (const [x, y] of tops) {
        const head = (y - HIDDEN + dy) * cell;
        for (let k = 0; k < 8; k++) {
          const a = Math.max(0, head - (length * cell * (k + 1)) / 8);
          const b = head - (length * cell * k) / 8;
          if (b > a) {
            ctx.fillStyle = mix("#0b110d", COLORS[piece.kind], 0.3 * (1 - k / 8));
            ctx.fillRect(x * cell + 8, a, cell - 16, b - a);
          }
        }
      }
    }
    for (const [x, y] of cellsOf(piece)) {
      const py = (y - HIDDEN + dy) * cell;
      if (py > -cell / 2) block(ctx, x * cell, Math.max(0, py), cell, COLORS[piece.kind], 0.08);
    }
  }
}

function drawNext() {
  const ctx = nextCtx;
  ctx.clearRect(0, 0, 110, 150);
  const queue = view.game ? view.game.queue.slice(0, 3) : [];
  queue.forEach((kind, i) => {
    const size = i === 0 ? 18 : 14;
    const cells = SHAPES[kind][0];
    const xs = cells.map(([x]) => x), ys = cells.map(([, y]) => y);
    const ox = 44 - ((Math.min(...xs) + Math.max(...xs) + 1) * size) / 2;
    const oy = 24 + i * 50 - ((Math.min(...ys) + Math.max(...ys) + 1) * size) / 2;
    const color = i === 0 ? COLORS[kind] : mix(COLORS[kind], "#101713", 0.35);
    for (const [cx, cy] of cells) block(ctx, ox + cx * size, oy + cy * size, size, color);
  });
}

function drawStats() {
  const game = view.game;
  if (!game) return;
  $("score").textContent = game.score.toLocaleString("en-US");
  $("lines").textContent = game.lines;
  $("pieces").textContent = game.pieces;
  const clears = Math.min(game.clears, GOAL);
  $("clears").textContent = clears;
  $("goal-meter").style.width = `${(100 * clears) / GOAL}%`;
  $("goal").classList.toggle("done", game.clears >= GOAL);
}

function frame() {
  drawWell();
  drawNext();
  drawStats();
  requestAnimationFrame(frame);
}

// ------------------------------------------------------------------ outcome sheet

function drawSheet(plans, chosen = -1) {
  const canvas = $("sheet");
  $("sheet-img").hidden = true;
  canvas.hidden = false;
  if (!plans.length) {
    setupCanvas(canvas, 0, 0);
    return;
  }
  const size = 16, tileW = WIDTH * size + 32;
  const tallest = Math.max(...plans.map((p) => Math.max(...heights(p.board))));
  let rows = Math.min(HEIGHT, Math.max(4, tallest + 2));
  rows += rows % 2;
  const perRow = Math.min(5, plans.length);
  const tileH = 32 + rows * size;
  const gridRows = Math.ceil(plans.length / perRow);
  const width = perRow * tileW, height = gridRows * tileH;
  const scale = Math.min(1, (canvas.parentElement.clientWidth || width) / width);
  const ctx = setupCanvas(canvas, width * scale, height * scale);
  ctx.scale(scale, scale);
  ctx.fillStyle = "#0a0d12";
  ctx.fillRect(0, 0, width, height);
  const names = labels(plans.length);
  plans.forEach((plan, i) => {
    const ox = (i % perRow) * tileW + 16, oy = Math.floor(i / perRow) * tileH;
    ctx.fillStyle = plan.lines ? "#ffd640" : "#ebf0f5";
    ctx.font = "22px 'DM Sans', system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(names[i] + (plan.lines ? `  +${plan.lines}` : ""), ox + (WIDTH * size) / 2, oy + 16);
    ctx.fillStyle = "#12161e";
    ctx.fillRect(ox, oy + 32, WIDTH * size, rows * size);
    const top = HIDDEN + HEIGHT - rows;
    plan.board.slice(top).forEach((row, y) => {
      row.forEach((kind, x) => { if (kind) block(ctx, ox + x * size, oy + 32 + y * size, size, COLORS[kind]); });
    });
    if (i === chosen) {
      ctx.strokeStyle = "#b4f784";
      ctx.lineWidth = 3;
      ctx.strokeRect(ox - 8, oy + 3, WIDTH * size + 16, tileH - 6);
    }
  });
  return { width, height, tokens: (width / 32) * (height / 32) };
}

// ------------------------------------------------------------------ call card

const card = $("card");
const t = (en, zh) => (document.documentElement.dataset.lang === "zh" ? zh : en);

function renderPlans(decision, reveal) {
  const list = $("plans");
  list.replaceChildren();
  decision.plans.forEach((plan, i) => {
    const li = document.createElement("li");
    const chosen = reveal && i === decision.chosen;
    li.className = chosen ? "chosen" : "";
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = decision.names[i];
    const facts = document.createElement("span");
    facts.className = "facts";
    const parts = [
      [plan.lines ? "good" : "", t(`clears ${plan.lines}`, `消除 ${plan.lines}`)],
      [plan.newHoles ? "bad" : "", t(`new holes ${plan.newHoles}`, `新空洞 ${plan.newHoles}`)],
      ["", t(`height ${plan.second.height}`, `高度 ${plan.second.height}`)],
    ];
    parts.forEach(([cls, text], k) => {
      const span = document.createElement("span");
      if (cls) span.className = cls;
      span.textContent = text;
      facts.append(span);
      if (k < parts.length - 1) facts.append(document.createTextNode("  ·  "));
    });
    const track = document.createElement("span");
    track.className = "track";
    const fill = document.createElement("i");
    track.append(fill);
    const pct = document.createElement("span");
    pct.className = "pct";
    pct.textContent = "—";
    li.append(badge, facts, track, pct);
    list.append(li);
    if (reveal) {
      const p = decision.probabilities[i];
      requestAnimationFrame(() => { fill.style.width = `${Math.max(p * 100, p > 0.002 ? 2 : 0)}%`; });
      pct.textContent = `${(p * 100).toFixed(1)}%`;
    }
  });
}

function showDecision(decision) {
  $("count").textContent = `${t("DECISION", "决策")} ${String(decision.number + 1).padStart(2, "0")}`;
  const n = decision.plans.length;
  $("subtitle").textContent = t(
    `${decision.falling} now, ${decision.next} next · ${n} plan${n > 1 ? "s" : ""} left after pruning`,
    `当前 ${decision.falling}，下一个 ${decision.next} · 剪枝后剩 ${n} 个方案`,
  );
  if (decision.imageUrl) {
    $("sheet").hidden = true;
    const img = $("sheet-img");
    img.src = decision.imageUrl;
    img.hidden = false;
  } else if (decision.mode === "text") {
    drawSheet([]);
  } else {
    drawSheet(decision.plans);
  }
  const image = decision.image;
  $("image-meta").textContent = image && image.tokens
    ? `${image.width} × ${image.height} px · ${image.tokens} ${t("image tokens", "个图像 token")}`
    : decision.mode === "text" ? t("text-only prompt: no image", "纯文字提示：不发送图片") : "";
  renderPlans(decision, false);
  $("metrics").replaceChildren();
  keys.hide();
}

function setMetrics(parts) {
  const box = $("metrics");
  box.replaceChildren();
  for (const [value, label, accent] of parts) {
    const span = document.createElement("span");
    const b = document.createElement("b");
    if (accent) b.className = "accent";
    b.textContent = value;
    span.append(b, document.createTextNode(` ${label}`));
    box.append(span);
  }
}

async function waitForAnswer(token, ms, promise) {
  card.classList.add("waiting");
  const started = performance.now();
  let done = false;
  const tick = () => {
    if (done || token !== session) return;
    setMetrics([[`${((performance.now() - started) * speed / 1000).toFixed(2)} s`, t("waiting for one token", "等待 1 个输出 token"), true]]);
    requestAnimationFrame(tick);
  };
  tick();
  try {
    const result = promise ? await promise : await wait(ms, token);
    check(token);
    return result;
  } finally {
    done = true;
    card.classList.remove("waiting");
  }
}

function reveal(decision) {
  renderPlans(decision, true);
  if (!decision.imageUrl && decision.mode !== "text") drawSheet(decision.plans, decision.chosen);
  if (decision.forced) {
    setMetrics([["1", t("plan dominates every other: no call needed", "个方案全面占优：无需调用")]]);
    return;
  }
  setMetrics([
    [`${(decision.clientMs / 1000).toFixed(2)} s`, t("round trip", "往返"), true],
    [`${(decision.serverMs / 1000).toFixed(2)} s`, t("server", "服务端")],
    [String(decision.inputTokens), t("input tokens", "输入 token")],
    [decision.confidence.toFixed(2), t("confidence", "置信度")],
  ]);
}

// ------------------------------------------------------------------ key strip

const ICONS = {
  left: '<svg viewBox="0 0 16 16"><path d="M13 8H4M7.5 4.5 4 8l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  right: '<svg viewBox="0 0 16 16"><path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  cw: '<svg viewBox="0 0 16 16"><path d="M12.6 9.2A4.8 4.8 0 1 1 11 4.4M11.2 1.8l.2 2.9-2.9.3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  ccw: '<svg viewBox="0 0 16 16"><path d="M3.4 9.2A4.8 4.8 0 1 0 5 4.4M4.8 1.8l-.2 2.9 2.9.3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  down: '<svg viewBox="0 0 16 16"><path d="M8 3v9M4.5 8.5 8 12l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  drop: '<svg viewBox="0 0 16 16"><path d="M8 2v7.5M4.8 6.6 8 9.8l3.2-3.2M3.5 13.5h9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

function pieceChip(kind) {
  const c = document.createElement("canvas");
  const ctx = setupCanvas(c, 22, 14);
  c.className = "piece-chip";
  const cells = SHAPES[kind][0];
  const xs = cells.map(([x]) => x), ys = cells.map(([, y]) => y);
  const s = 5.5;
  const ox = 11 - ((Math.min(...xs) + Math.max(...xs) + 1) * s) / 2;
  const oy = 7 - ((Math.min(...ys) + Math.max(...ys) + 1) * s) / 2;
  for (const [x, y] of cells) block(ctx, ox + x * s, oy + y * s, s, COLORS[kind]);
  return c;
}

const keys = {
  el: $("keys"),
  caps: [],
  hide() { this.el.replaceChildren(); this.caps = []; },
  show(sequences, kinds) {
    this.el.replaceChildren();
    this.caps = sequences.map((sequence, move) => {
      if (move) {
        const then = document.createElement("span");
        then.className = "then";
        then.textContent = t("then", "然后");
        this.el.append(then);
      }
      this.el.append(pieceChip(kinds[move]));
      return sequence.map((key) => {
        const cap = document.createElement("span");
        cap.className = "key";
        cap.innerHTML = ICONS[key];
        cap.title = key;
        this.el.append(cap);
        return cap;
      });
    });
  },
  activate(move, index) {
    this.caps.forEach((caps, m) => caps.forEach((cap, i) => {
      const order = m < move || (m === move && i < index) ? "done" : m === move && i === index ? "active" : "";
      cap.className = `key ${order}`.trim();
    }));
  },
};

// ------------------------------------------------------------------ playing a decision

async function playMoves(game, plan, token) {
  const sequences = [plan.first.keys, plan.second.keys];
  keys.show(sequences, [game.piece.kind, game.queue[0]]);
  for (let move = 0; move < 2; move++) {
    for (let i = 0; i < sequences[move].length; i++) {
      const key = sequences[move][i];
      keys.activate(move, i);
      if (key !== "drop") {
        if (!game.press(key)) throw new Error(`Replay diverged: ${key} had no effect`);
        await wait(PACE.key, token);
        continue;
      }
      const start = game.piece.y;
      const landing = dropped(game.board, game.piece);
      view.drop = { piece: landing, from: start, y: start };
      await animate(40 + 7 * (landing.y - start), token, (p) => {
        view.drop.y = start + (landing.y - start) * easeIn(p);
      });
      view.drop = null;
      if (!game.press("drop")) throw new Error("Replay diverged on drop");
      const clear = game.lastClear;
      if (clear) {
        view.hidePiece = true;
        view.flash = { board: clear.settled, rows: clear.full, t: 0 };
        await animate(PACE.flash, token, (p) => { view.flash.t = p; });
        view.flash = null;
        view.collapse = { board: clear.settled, rows: clear.full, t: 0 };
        await animate(PACE.collapse, token, (p) => { view.collapse.t = p; });
        view.collapse = null;
        view.hidePiece = false;
      } else {
        await wait(PACE.lock, token);
      }
      if (game.over) return;
    }
  }
  keys.activate(2, 0);
}

function decisionFor(game, number, mode) {
  const plans = frontier(game.plans());
  return { number, mode, plans, names: labels(plans.length), falling: game.piece.kind, next: game.queue[0] };
}

// ------------------------------------------------------------------ replay mode

let replays = null;
async function loadReplays() {
  if (replays) return replays;
  const response = await fetch("../report/replays.json");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  replays = await response.json();
  return replays;
}

function fillSeeds() {
  const profile = replays.profiles[$("replay-profile").value];
  const mode = $("replay-mode").value;
  const select = $("replay-seed");
  const current = select.value;
  select.replaceChildren();
  for (const game of profile.games.filter((g) => g.mode === mode)) {
    const option = document.createElement("option");
    option.value = game.seed;
    option.textContent = `${game.seed} · ${game.result.lines} ${t("lines", "行")}`;
    select.append(option);
  }
  if ([...select.options].some((o) => o.value === current)) select.value = current;
}

async function runReplay() {
  const token = ++session;
  const profileName = $("replay-profile").value;
  const profile = replays.profiles[profileName];
  const run = profile.games.find((g) => g.mode === $("replay-mode").value && String(g.seed) === $("replay-seed").value);
  const game = new Game(run.seed);
  view.game = game;
  hideOverlay();
  status("replay-status", `${profile.model.split("/").pop()} · ${profile.quant}`);
  setToggle("replay-toggle", true);
  try {
    for (const [number, record] of run.decisions.entries()) {
      const decision = decisionFor(game, number, run.mode);
      const chosen = decision.names.indexOf(record.c);
      if (chosen < 0 || decision.plans.length !== record.p.length) throw new Error("Replay diverged from the recording");
      Object.assign(decision, {
        chosen, probabilities: record.p, clientMs: record.ms, serverMs: record.s, inputTokens: record.t,
        confidence: record.k, forced: record.p.length === 1,
        image: record.i ? { width: record.i[0], height: record.i[1], tokens: record.i[2] } : null,
      });
      showDecision(decision);
      if (decision.forced) await wait(PACE.forced, token);
      else await waitForAnswer(token, record.ms);
      reveal(decision);
      await wait(decision.forced ? 0 : PACE.answer + PACE.settle, token);
      await playMoves(game, decision.plans[chosen], token);
    }
    const r = run.result;
    showOverlay(
      r.topped_out ? t("Topped out", "堆满结束") : t("100 pieces played", "已下完 100 个方块"),
      t(`${r.lines} lines · ${r.clears} clears · score ${r.score.toLocaleString("en-US")}`,
        `${r.lines} 行 · ${r.clears} 次消除 · 得分 ${r.score.toLocaleString("en-US")}`),
    );
  } catch (error) {
    if (!(error instanceof Cancelled)) status("replay-status", error.message, "error");
  } finally {
    if (token === session) setToggle("replay-toggle", false);
  }
}

// ------------------------------------------------------------------ live mode

async function checkLive() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    status("live-status", `${t("connected", "已连接")} · ${body.model}`, "ok");
    return true;
  } catch {
    status("live-status", t("needs serve.py and a local OpenJev model", "需要本机运行 serve.py 与 OpenJev 模型"), "error");
    return false;
  }
}

async function runLive() {
  const token = ++session;
  if (!(await checkLive())) return;
  const game = new Game(Number($("live-seed").value) || 0);
  view.game = game;
  hideOverlay();
  setToggle("live-toggle", true);
  const mode = $("live-mode").value;
  try {
    for (let number = 0; !game.over && game.pieces + 2 <= 100; number++) {
      const decision = decisionFor(game, number, mode);
      if (!decision.plans.length) { game.over = true; break; }
      showDecision(decision);
      let record;
      if (decision.plans.length === 1) {
        record = { chosen: "A", options: [{ probability: 1 }], forced: true, client_ms: 0, server_ms: 0, input_tokens: 0, confidence: 1 };
        await wait(PACE.forced, token);
      } else {
        const started = performance.now();
        const request = fetch("/api/decide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ board: game.board, falling: game.piece.kind, queue: game.queue, lines: game.lines, mode, number }),
        }).then(async (r) => {
          const body = await r.json();
          if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
          return body;
        });
        record = await waitForAnswer(token, 0, request);
        record.client_ms = performance.now() - started;
      }
      const chosen = decision.names.indexOf(record.chosen);
      if (chosen < 0 || record.options.length !== decision.plans.length) throw new Error("Server and browser disagree on the options");
      Object.assign(decision, {
        chosen, probabilities: record.options.map((o) => o.probability), clientMs: record.client_ms,
        serverMs: record.server_ms, inputTokens: record.input_tokens, confidence: record.confidence,
        forced: Boolean(record.forced), image: record.image, imageUrl: record.image_url,
      });
      if (decision.imageUrl) showDecision(decision);
      reveal(decision);
      await wait(decision.forced ? 0 : PACE.answer + PACE.settle, token);
      await playMoves(game, decision.plans[chosen], token);
    }
    showOverlay(game.over ? t("Topped out", "堆满结束") : t("100 pieces played", "已下完 100 个方块"),
      t(`${game.lines} lines · score ${game.score.toLocaleString("en-US")}`, `${game.lines} 行 · 得分 ${game.score.toLocaleString("en-US")}`));
  } catch (error) {
    if (!(error instanceof Cancelled)) status("live-status", error.message, "error");
  } finally {
    if (token === session) setToggle("live-toggle", false);
  }
}

// ------------------------------------------------------------------ play mode

let gravity = null;
let paused = false;
function startPlay() {
  ++session;
  clearInterval(gravity);
  const game = new Game(Number($("play-seed").value) || 0);
  view.game = game;
  paused = false;
  hideOverlay();
  keys.hide();
  let landed = null;
  const tick = () => {
    if (paused || game.over) return;
    if (game.fall()) {
      landed = null;
    } else if (landed === null) {
      landed = performance.now(); // lock delay: one more tick to slide or rotate
    } else if (performance.now() - landed >= 450) {
      landed = null;
      game.lock();
    }
    if (game.over) endPlay(game);
  };
  const schedule = () => {
    clearInterval(gravity);
    gravity = setInterval(() => { tick(); if (game.level !== level) { level = game.level; schedule(); } }, Math.max(90, 800 * 0.85 ** (game.level - 1)));
  };
  let level = game.level;
  schedule();
}
function endPlay(game) {
  clearInterval(gravity);
  showOverlay(t("Game over", "游戏结束"), t(`${game.lines} lines · score ${game.score.toLocaleString("en-US")} · press R`, `${game.lines} 行 · 得分 ${game.score.toLocaleString("en-US")} · 按 R 重开`));
}
const KEYMAP = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "cw", x: "cw", X: "cw", z: "ccw", Z: "ccw", ArrowDown: "down", " ": "drop" };
function playKey(key) {
  const game = view.game;
  if (currentMode !== "play" || !game || game.over || paused) return;
  game.press(key);
  if (game.over) endPlay(game);
}
document.addEventListener("keydown", (event) => {
  if (currentMode !== "play" || (event.target instanceof Element && event.target.closest("input, select"))) return;
  if (event.key === "p" || event.key === "P") {
    paused = !paused;
    if (paused) showOverlay(t("Paused", "已暂停"), t("press P to continue", "按 P 继续")); else hideOverlay();
    return;
  }
  if (event.key === "r" || event.key === "R") { startPlay(); return; }
  const key = KEYMAP[event.key];
  if (!key) return;
  event.preventDefault();
  playKey(key);
});
document.querySelectorAll("#touch button").forEach((button) => {
  button.innerHTML = ICONS[button.dataset.key];
  button.addEventListener("click", () => playKey(button.dataset.key));
});

// ------------------------------------------------------------------ chrome

function status(id, text, kind = "") {
  const el = $(id);
  el.textContent = text;
  el.className = `status ${kind}`.trim();
}
function setToggle(id, running) {
  const button = $(id);
  button.dataset.running = running ? "1" : "";
  button.querySelectorAll("[lang]").forEach((s) => s.remove());
  const label = { "replay-toggle": ["Play", "播放", "Stop", "停止"], "live-toggle": ["Let Jev play", "让 Jev 来玩", "Stop", "停止"] }[id];
  button.firstChild.textContent = running ? "■ " : "▶ ";
  const en = document.createElement("span"); en.lang = "en"; en.textContent = running ? label[2] : label[0];
  const zh = document.createElement("span"); zh.lang = "zh"; zh.textContent = running ? label[3] : label[1];
  button.append(en, zh);
}
function showOverlay(title, text) {
  $("overlay-title").textContent = title;
  $("overlay-text").textContent = text;
  $("overlay").hidden = false;
}
function hideOverlay() { $("overlay").hidden = true; }

let currentMode = "replay";
function setMode(mode) {
  currentMode = mode;
  ++session;
  clearInterval(gravity);
  document.querySelectorAll(".modes button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.mode === mode)));
  for (const m of ["replay", "live", "play"]) $(`controls-${m}`).hidden = m !== mode;
  $("card").hidden = mode === "play";
  $("keys").hidden = mode === "play";
  $("help").hidden = mode !== "play";
  $("stage").classList.toggle("playing", mode === "play");
  setToggle("replay-toggle", false);
  setToggle("live-toggle", false);
  if (mode === "play") startPlay();
  if (mode === "live") checkLive();
  try { history.replaceState(null, "", `#${mode}`); } catch {}
}
document.querySelectorAll(".modes button").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
window.addEventListener("hashchange", () => {
  const mode = location.hash.slice(1);
  if (["replay", "live", "play"].includes(mode) && mode !== currentMode) setMode(mode);
});

$("replay-toggle").addEventListener("click", async () => {
  if ($("replay-toggle").dataset.running) { ++session; setToggle("replay-toggle", false); return; }
  try { await loadReplays(); } catch (error) { status("replay-status", `${t("cannot load replays", "无法加载回放数据")}: ${error.message}`, "error"); return; }
  runReplay();
});
$("live-toggle").addEventListener("click", () => {
  if ($("live-toggle").dataset.running) { ++session; setToggle("live-toggle", false); return; }
  runLive();
});
$("play-start").addEventListener("click", startPlay);
for (const id of ["replay-profile", "replay-mode"]) $(id).addEventListener("change", () => { if (replays) fillSeeds(); });
document.querySelectorAll(".speed button").forEach((b) => b.addEventListener("click", () => {
  speed = Number(b.dataset.speed);
  document.querySelectorAll(".speed button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
}));

function setLang(lang) {
  document.documentElement.dataset.lang = lang;
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  $("lang").textContent = lang === "zh" ? "English" : "中文";
  try { localStorage.setItem("openjev-tetris-lang", lang); } catch {}
  if (replays) fillSeeds();
}
$("lang").addEventListener("click", () => setLang(document.documentElement.dataset.lang === "zh" ? "en" : "zh"));

// ------------------------------------------------------------------ start

let initialLang = navigator.language?.startsWith("zh") ? "zh" : "en";
try { initialLang = localStorage.getItem("openjev-tetris-lang") || initialLang; } catch {}
setLang(initialLang);
sizeCanvases();
window.addEventListener("resize", () => { sizeCanvases(); });
view.game = new Game(101);
requestAnimationFrame(frame);
const start = location.hash.slice(1);
setMode(["replay", "live", "play"].includes(start) ? start : "replay");
loadReplays().then(() => { fillSeeds(); status("replay-status", t("ready", "就绪")); })
  .catch(() => status("replay-status", t("serve this folder over HTTP to load replays", "请通过 HTTP 访问本目录以加载回放"), "error"));
