"""Deterministic Tetris engine shared by the Jev player, the replay and the browser game.

Guideline rules: a 10 x 20 visible well with two hidden rows above it, a seeded 7-bag
randomizer (mulberry32, mirrored in web/tetris.js), SRS rotation with wall kicks, soft
and hard drop. Standard library only.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

WIDTH, HEIGHT, HIDDEN = 10, 20, 2
ROWS = HEIGHT + HIDDEN
KINDS = "IJLOSTZ"
KEYS = ("left", "right", "cw", "ccw", "down", "drop")
LINE_SCORES = (0, 100, 300, 500, 800)

_SPAWN_SHAPES = {
    "I": ((0, 1), (1, 1), (2, 1), (3, 1)),
    "J": ((0, 0), (0, 1), (1, 1), (2, 1)),
    "L": ((2, 0), (0, 1), (1, 1), (2, 1)),
    "O": ((1, 0), (2, 0), (1, 1), (2, 1)),
    "S": ((1, 0), (2, 0), (0, 1), (1, 1)),
    "T": ((1, 0), (0, 1), (1, 1), (2, 1)),
    "Z": ((0, 0), (1, 0), (1, 1), (2, 1)),
}


def _rotations(kind: str) -> tuple[tuple[tuple[int, int], ...], ...]:
    """SRS states 0, R, 2, L: true rotation inside the piece's bounding box."""
    states = [_SPAWN_SHAPES[kind]]
    size = 4 if kind == "I" else 3
    for _ in range(3):
        if kind == "O":  # O never changes position when rotated
            states.append(states[-1])
        else:
            states.append(tuple(sorted((size - 1 - y, x) for x, y in states[-1])))
    return tuple(states)


SHAPES = {kind: _rotations(kind) for kind in KINDS}

# SRS wall kicks, written with y pointing up as in the guideline tables.
_KICKS = {
    (0, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (1, 0): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (1, 2): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (2, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (2, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (3, 2): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (3, 0): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (0, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
}
_KICKS_I = {
    (0, 1): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (1, 0): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
    (2, 1): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (2, 3): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (3, 0): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
}


def mulberry32(seed: int):
    """Small seeded PRNG with a bit-exact JavaScript twin, so both engines deal the same bag."""
    state = seed & 0xFFFFFFFF

    def random() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((state ^ (state >> 15)) * (state | 1)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return (t ^ (t >> 14)) / 4294967296

    return random


class Bag:
    """7-bag randomizer: every run of seven pieces contains each piece exactly once."""

    def __init__(self, seed: int):
        self.random = mulberry32(seed)
        self.pending: list[str] = []

    def next(self) -> str:
        if not self.pending:
            bag = list(KINDS)
            for i in range(len(bag) - 1, 0, -1):
                j = int(self.random() * (i + 1))
                bag[i], bag[j] = bag[j], bag[i]
            self.pending = bag
        return self.pending.pop(0)


@dataclass(frozen=True)
class Piece:
    kind: str
    rot: int
    x: int
    y: int

    def cells(self) -> tuple[tuple[int, int], ...]:
        return tuple((self.x + cx, self.y + cy) for cx, cy in SHAPES[self.kind][self.rot])

    def moved(self, dx: int = 0, dy: int = 0, rot: int | None = None) -> Piece:
        return Piece(self.kind, self.rot if rot is None else rot, self.x + dx, self.y + dy)


Board = list[list[str | None]]


def empty_board() -> Board:
    return [[None] * WIDTH for _ in range(ROWS)]


def spawn_piece(kind: str) -> Piece:
    """Spawn centred with the top of the piece on the first visible row."""
    top = min(y for _, y in SHAPES[kind][0])
    return Piece(kind, 0, 3, HIDDEN - top)


def fits(board: Board, cells) -> bool:
    return all(0 <= x < WIDTH and 0 <= y < ROWS and board[y][x] is None for x, y in cells)


def shifted(board: Board, piece: Piece, dx: int, dy: int = 0) -> Piece | None:
    moved = piece.moved(dx, dy)
    return moved if fits(board, moved.cells()) else None


def rotated(board: Board, piece: Piece, turn: int) -> Piece | None:
    """Rotate clockwise (+1) or counter-clockwise (-1) with SRS kicks; None if blocked."""
    if piece.kind == "O":
        return piece
    target = (piece.rot + turn) % 4
    kicks = (_KICKS_I if piece.kind == "I" else _KICKS)[(piece.rot, target)]
    for dx, dy in kicks:
        candidate = piece.moved(dx, -dy, rot=target)
        if fits(board, candidate.cells()):
            return candidate
    return None


def dropped(board: Board, piece: Piece) -> Piece:
    while (lower := shifted(board, piece, 0, 1)) is not None:
        piece = lower
    return piece


def apply_key(board: Board, piece: Piece, key: str) -> Piece | None:
    """Move a piece with one key press. None means the key had no legal effect."""
    if key == "left":
        return shifted(board, piece, -1)
    if key == "right":
        return shifted(board, piece, 1)
    if key == "cw":
        return rotated(board, piece, 1)
    if key == "ccw":
        return rotated(board, piece, -1)
    if key == "down":
        return shifted(board, piece, 0, 1)
    if key == "drop":
        return dropped(board, piece)
    raise ValueError(f"Unknown key {key!r}; expected one of {KEYS}")


def lock(board: Board, piece: Piece) -> tuple[Board, list[int]]:
    """Return the board after locking the piece and removing full rows, plus the full rows."""
    grid = [row[:] for row in board]
    for x, y in piece.cells():
        grid[y][x] = piece.kind
    full = [y for y, row in enumerate(grid) if all(row)]
    kept = [row for y, row in enumerate(grid) if y not in full]
    return [[None] * WIDTH for _ in full] + kept, full


def heights(board: Board) -> list[int]:
    result = []
    for x in range(WIDTH):
        top = next((y for y in range(ROWS) if board[y][x] is not None), ROWS)
        result.append(ROWS - top)
    return result


def bumpiness(column_heights: list[int]) -> int:
    """Total height difference between neighbouring columns."""
    return sum(abs(a - b) for a, b in zip(column_heights, column_heights[1:], strict=False))


def holes(board: Board) -> int:
    """Empty cells with at least one filled cell above them in the same column."""
    count = 0
    for x in range(WIDTH):
        covered = False
        for y in range(ROWS):
            if board[y][x] is not None:
                covered = True
            elif covered:
                count += 1
    return count


@dataclass(frozen=True)
class Placement:
    """One legal final position for the falling piece and the keys that reach it."""

    keys: tuple[str, ...]
    piece: Piece
    board: Board = field(repr=False, compare=False)
    cleared: tuple[int, ...]
    holes: int
    new_holes: int
    height: int
    aggregate: int
    bumpiness: int

    @property
    def lines(self) -> int:
        return len(self.cleared)

    @property
    def columns(self) -> tuple[int, int]:
        xs = [x for x, _ in self.piece.cells()]
        return min(xs), max(xs)

    def value(self) -> float:
        """Reference evaluation (Yiyuan Lee's tuned weights); used for comparison only."""
        return (
            -0.510066 * self.aggregate
            + 0.760666 * self.lines
            - 0.35663 * self.holes
            - 0.184483 * self.bumpiness
        )


def placements(board: Board, piece: Piece) -> list[Placement]:
    """Every distinct landing position reachable by rotating, shifting, then hard dropping."""
    before = holes(board)
    found: dict[frozenset, Placement] = {}
    for rotation in ((), ("cw",), ("cw", "cw"), ("ccw",)):
        start = piece
        for key in rotation:
            start = apply_key(board, start, key) if start else None
        if start is None:
            continue
        for direction, dx in (("left", -1), ("right", 1)):
            current, keys = start, list(rotation)
            while current is not None:
                final = dropped(board, current)
                cells = frozenset(final.cells())
                sequence = (*keys, "drop")
                if cells not in found or len(sequence) < len(found[cells].keys):
                    after, full = lock(board, final)
                    column_heights = heights(after)
                    covered = holes(after)
                    found[cells] = Placement(
                        keys=sequence,
                        piece=final,
                        board=after,
                        cleared=tuple(full),
                        holes=covered,
                        new_holes=covered - before,
                        height=max(column_heights),
                        aggregate=sum(column_heights),
                        bumpiness=bumpiness(column_heights),
                    )
                current = shifted(board, current, dx)
                keys.append(direction)
    return sorted(found.values(), key=lambda p: (p.columns, p.piece.rot, p.keys))


@dataclass(frozen=True)
class Plan:
    """Placements for the falling piece and the next piece: one decision, two moves."""

    first: Placement
    second: Placement
    holes_before: int

    @property
    def keys(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return self.first.keys, self.second.keys

    @property
    def board(self) -> Board:
        return self.second.board

    @property
    def lines(self) -> int:
        return self.first.lines + self.second.lines

    @property
    def new_holes(self) -> int:
        return max(0, self.second.holes - self.holes_before)

    def facts(self) -> tuple[int, ...]:
        """Measured outcome, oriented so that smaller is better in every position."""
        s = self.second
        return (-self.lines, s.holes, s.height, s.aggregate, s.bumpiness)

    def value(self) -> float:
        """Reference evaluation of the final well; used for comparison only."""
        s = self.second
        return (
            -0.510066 * s.aggregate
            + 0.760666 * self.lines
            - 0.35663 * s.holes
            - 0.184483 * s.bumpiness
        )


def plans(board: Board, piece: Piece, upcoming: str) -> list[Plan]:
    """Every pair of placements for the falling piece and the next one."""
    before = holes(board)
    result = []
    for first in placements(board, piece):
        spawn = spawn_piece(upcoming)
        if not fits(first.board, spawn.cells()):
            continue  # this placement tops out before the next piece can enter
        result.extend(Plan(first, second, before) for second in placements(first.board, spawn))
    return result


def frontier(candidates: list[Plan]) -> list[Plan]:
    """Keep plans that no other plan matches or beats on every measured fact.

    Facts: rows cleared, holes, stack height, aggregate height and bumpiness. No weights
    are involved, so every trade-off between them is left to the decision maker. Plans
    with identical facts collapse to the one with the fewest key presses. The result is
    ordered left to right, which carries no information about quality.
    """
    facts = [p.facts() for p in candidates]
    unique: dict[tuple[int, ...], Plan] = {}
    for plan, fp in zip(candidates, facts, strict=True):
        if any(fq != fp and all(a <= b for a, b in zip(fq, fp, strict=True)) for fq in facts):
            continue
        presses = len(plan.first.keys) + len(plan.second.keys)
        held = unique.get(fp)
        if held is None or presses < len(held.first.keys) + len(held.second.keys):
            unique[fp] = plan
    return sorted(
        unique.values(),
        key=lambda p: (p.first.columns, p.first.piece.rot, p.second.columns, p.second.piece.rot),
    )


class Game:
    """Turn-based game state: a falling piece, a preview queue and a scored well."""

    def __init__(self, seed: int = 7, preview: int = 3):
        self.seed = seed
        self.board = empty_board()
        self.bag = Bag(seed)
        self.queue = deque(self.bag.next() for _ in range(preview))
        self.piece: Piece | None = None
        self.score = self.lines = self.clears = self.pieces = 0
        self.over = False
        self.spawn()

    @property
    def level(self) -> int:
        return self.lines // 10 + 1

    def spawn(self) -> None:
        kind = self.queue.popleft()
        self.queue.append(self.bag.next())
        piece = spawn_piece(kind)
        self.piece = piece
        if not fits(self.board, piece.cells()):
            self.over = True

    def press(self, key: str) -> bool:
        """Apply one key press. Returns False when the key had no effect."""
        if self.over or self.piece is None:
            return False
        moved = apply_key(self.board, self.piece, key)
        if moved is None:
            return False
        if key == "drop":
            self.score += 2 * (moved.y - self.piece.y)
            self.piece = moved
            self.lock()
            return True
        if key == "down":
            self.score += 1
        self.piece = moved
        return True

    def lock(self) -> list[int]:
        piece = self.piece
        self.board, full = lock(self.board, piece)
        self.pieces += 1
        if full:
            self.score += LINE_SCORES[len(full)] * self.level
            self.lines += len(full)
            self.clears += 1
        if all(y < HIDDEN for _, y in piece.cells()):
            self.over = True  # lock out: the piece settled entirely above the visible well
            return full
        self.spawn()
        return full

    def options(self) -> list[Placement]:
        return placements(self.board, self.piece) if self.piece and not self.over else []

    def plans(self) -> list[Plan]:
        return plans(self.board, self.piece, self.queue[0]) if self.piece and not self.over else []
