// Tetris engine for the browser, mirroring tetris.py move for move.
// Same 10 x 20 well with two hidden rows, mulberry32 7-bag, SRS rotation and wall kicks,
// placement enumeration and dominance frontier, so recorded runs replay exactly.

export const WIDTH = 10, HEIGHT = 20, HIDDEN = 2, ROWS = HEIGHT + HIDDEN;
export const KINDS = "IJLOSTZ";
export const LINE_SCORES = [0, 100, 300, 500, 800];

const SPAWN_SHAPES = {
  I: [[0, 1], [1, 1], [2, 1], [3, 1]],
  J: [[0, 0], [0, 1], [1, 1], [2, 1]],
  L: [[2, 0], [0, 1], [1, 1], [2, 1]],
  O: [[1, 0], [2, 0], [1, 1], [2, 1]],
  S: [[1, 0], [2, 0], [0, 1], [1, 1]],
  T: [[1, 0], [0, 1], [1, 1], [2, 1]],
  Z: [[0, 0], [1, 0], [1, 1], [2, 1]],
};

function sortCells(cells) {
  return cells.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}

function rotations(kind) {
  const states = [SPAWN_SHAPES[kind]];
  const size = kind === "I" ? 4 : 3;
  for (let i = 0; i < 3; i++) {
    const last = states[states.length - 1];
    states.push(kind === "O" ? last : sortCells(last.map(([x, y]) => [size - 1 - y, x])));
  }
  return states;
}

export const SHAPES = Object.fromEntries([...KINDS].map((k) => [k, rotations(k)]));

// SRS wall kicks with y pointing up, as in the guideline tables.
const KICKS = {
  "0,1": [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  "1,0": [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  "1,2": [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  "2,1": [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  "2,3": [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
  "3,2": [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  "3,0": [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  "0,3": [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
};
const KICKS_I = {
  "0,1": [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  "1,0": [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  "1,2": [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
  "2,1": [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  "2,3": [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  "3,2": [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  "3,0": [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  "0,3": [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
};

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class Bag {
  constructor(seed) {
    this.random = mulberry32(seed);
    this.pending = [];
  }
  next() {
    if (!this.pending.length) {
      const bag = [...KINDS];
      for (let i = bag.length - 1; i > 0; i--) {
        const j = Math.floor(this.random() * (i + 1));
        [bag[i], bag[j]] = [bag[j], bag[i]];
      }
      this.pending = bag;
    }
    return this.pending.shift();
  }
}

export const piece = (kind, rot, x, y) => ({ kind, rot, x, y });
export const cellsOf = (p) => SHAPES[p.kind][p.rot].map(([cx, cy]) => [p.x + cx, p.y + cy]);
export const emptyBoard = () => Array.from({ length: ROWS }, () => Array(WIDTH).fill(null));
export const copyBoard = (board) => board.map((row) => row.slice());

export function spawnPiece(kind) {
  const top = Math.min(...SHAPES[kind][0].map(([, y]) => y));
  return piece(kind, 0, 3, HIDDEN - top);
}

export function fits(board, cells) {
  return cells.every(([x, y]) => x >= 0 && x < WIDTH && y >= 0 && y < ROWS && board[y][x] === null);
}

export function shifted(board, p, dx, dy = 0) {
  const moved = piece(p.kind, p.rot, p.x + dx, p.y + dy);
  return fits(board, cellsOf(moved)) ? moved : null;
}

export function rotated(board, p, turn) {
  if (p.kind === "O") return p;
  const target = (p.rot + turn + 4) % 4;
  const kicks = (p.kind === "I" ? KICKS_I : KICKS)[`${p.rot},${target}`];
  for (const [dx, dy] of kicks) {
    const candidate = piece(p.kind, target, p.x + dx, p.y - dy);
    if (fits(board, cellsOf(candidate))) return candidate;
  }
  return null;
}

export function dropped(board, p) {
  let lower;
  while ((lower = shifted(board, p, 0, 1))) p = lower;
  return p;
}

export function applyKey(board, p, key) {
  switch (key) {
    case "left": return shifted(board, p, -1);
    case "right": return shifted(board, p, 1);
    case "cw": return rotated(board, p, 1);
    case "ccw": return rotated(board, p, -1);
    case "down": return shifted(board, p, 0, 1);
    case "drop": return dropped(board, p);
    default: throw new Error(`Unknown key ${key}`);
  }
}

export function settle(board, p) {
  const grid = copyBoard(board);
  for (const [x, y] of cellsOf(p)) grid[y][x] = p.kind;
  return grid;
}

export function lock(board, p) {
  const grid = settle(board, p);
  const full = [];
  grid.forEach((row, y) => { if (row.every(Boolean)) full.push(y); });
  const kept = grid.filter((_, y) => !full.includes(y));
  return { board: [...full.map(() => Array(WIDTH).fill(null)), ...kept], full, settled: grid };
}

export function heights(board) {
  const result = [];
  for (let x = 0; x < WIDTH; x++) {
    let top = ROWS;
    for (let y = 0; y < ROWS; y++) if (board[y][x] !== null) { top = y; break; }
    result.push(ROWS - top);
  }
  return result;
}

export function bumpiness(h) {
  let total = 0;
  for (let i = 0; i + 1 < h.length; i++) total += Math.abs(h[i] - h[i + 1]);
  return total;
}

export function holes(board) {
  let count = 0;
  for (let x = 0; x < WIDTH; x++) {
    let covered = false;
    for (let y = 0; y < ROWS; y++) {
      if (board[y][x] !== null) covered = true;
      else if (covered) count++;
    }
  }
  return count;
}

const columnsOf = (p) => {
  const xs = cellsOf(p).map(([x]) => x);
  return [Math.min(...xs), Math.max(...xs)];
};

// Python tuple ordering for (columns, rot, keys).
function compareSeq(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return a.length - b.length;
}

export function placements(board, start) {
  const before = holes(board);
  const found = new Map();
  for (const rotation of [[], ["cw"], ["cw", "cw"], ["ccw"]]) {
    let p = start;
    for (const key of rotation) p = p ? applyKey(board, p, key) : null;
    if (!p) continue;
    for (const [direction, dx] of [["left", -1], ["right", 1]]) {
      let current = p;
      const keys = [...rotation];
      while (current) {
        const final = dropped(board, current);
        const id = cellsOf(final).map(([x, y]) => `${x},${y}`).sort().join(";");
        const sequence = [...keys, "drop"];
        if (!found.has(id) || sequence.length < found.get(id).keys.length) {
          const { board: after, full } = lock(board, final);
          const h = heights(after);
          const covered = holes(after);
          found.set(id, {
            keys: sequence, piece: final, board: after, cleared: full, lines: full.length,
            holes: covered, newHoles: covered - before, height: Math.max(...h),
            aggregate: h.reduce((a, b) => a + b, 0), bumpiness: bumpiness(h),
            columns: columnsOf(final),
          });
        }
        current = shifted(board, current, dx);
        keys.push(direction);
      }
    }
  }
  return [...found.values()].sort((a, b) =>
    compareSeq(a.columns, b.columns) || a.piece.rot - b.piece.rot || compareSeq(a.keys, b.keys));
}

export function plans(board, falling, upcoming) {
  const before = holes(board);
  const result = [];
  for (const first of placements(board, falling)) {
    const spawn = spawnPiece(upcoming);
    if (!fits(first.board, cellsOf(spawn))) continue;
    for (const second of placements(first.board, spawn)) {
      const lines = first.lines + second.lines;
      result.push({
        first, second, lines, board: second.board,
        newHoles: Math.max(0, second.holes - before),
        facts: [-lines, second.holes, second.height, second.aggregate, second.bumpiness],
        value: -0.510066 * second.aggregate + 0.760666 * lines - 0.35663 * second.holes
          - 0.184483 * second.bumpiness,
      });
    }
  }
  return result;
}

export function frontier(candidates) {
  const facts = candidates.map((p) => p.facts);
  const unique = new Map();
  candidates.forEach((plan, i) => {
    const fp = facts[i];
    const dominated = facts.some((fq) => fq.some((v, k) => v !== fp[k]) && fq.every((v, k) => v <= fp[k]));
    if (dominated) return;
    const id = fp.join(",");
    const presses = plan.first.keys.length + plan.second.keys.length;
    const held = unique.get(id);
    if (!held || presses < held.first.keys.length + held.second.keys.length) unique.set(id, plan);
  });
  return [...unique.values()].sort((a, b) =>
    compareSeq(a.first.columns, b.first.columns) || a.first.piece.rot - b.first.piece.rot
    || compareSeq(a.second.columns, b.second.columns) || a.second.piece.rot - b.second.piece.rot);
}

export function labels(count) {
  const singles = [...Array(26)].map((_, i) => String.fromCharCode(65 + i));
  const doubles = singles.flatMap((a) => singles.map((b) => a + b));
  return [...singles, ...doubles].slice(0, count);
}

export class Game {
  constructor(seed = 7, preview = 3) {
    this.seed = seed;
    this.board = emptyBoard();
    this.bag = new Bag(seed);
    this.queue = Array.from({ length: preview }, () => this.bag.next());
    this.piece = null;
    this.score = 0; this.lines = 0; this.clears = 0; this.pieces = 0;
    this.over = false;
    this.lastClear = null;
    this.spawn();
  }
  get level() { return Math.floor(this.lines / 10) + 1; }
  spawn() {
    const kind = this.queue.shift();
    this.queue.push(this.bag.next());
    this.piece = spawnPiece(kind);
    if (!fits(this.board, cellsOf(this.piece))) this.over = true;
  }
  fall() {
    // Gravity: one row down without scoring; false when the piece has landed.
    if (this.over || !this.piece) return false;
    const moved = shifted(this.board, this.piece, 0, 1);
    if (!moved) return false;
    this.piece = moved;
    return true;
  }
  press(key) {
    if (this.over || !this.piece) return false;
    const moved = applyKey(this.board, this.piece, key);
    if (!moved) return false;
    if (key === "drop") {
      this.score += 2 * (moved.y - this.piece.y);
      this.piece = moved;
      this.lock();
      return true;
    }
    if (key === "down") this.score += 1;
    this.piece = moved;
    return true;
  }
  lock() {
    const p = this.piece;
    const { board, full, settled } = lock(this.board, p);
    this.board = board;
    this.pieces += 1;
    this.lastClear = full.length ? { full, settled } : null;
    if (full.length) {
      this.score += LINE_SCORES[full.length] * this.level;
      this.lines += full.length;
      this.clears += 1;
    }
    if (cellsOf(p).every(([, y]) => y < HIDDEN)) { this.over = true; return; }
    this.spawn();
  }
  plans() {
    return this.piece && !this.over ? plans(this.board, this.piece, this.queue[0]) : [];
  }
}
