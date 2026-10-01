"""Render the well for Jev and for people.

Qwen3.5's vision encoder cuts images into 16 px patches and merges each 2 x 2 group into
one visual token, so a 32 px square is one token. The Jev view draws every board cell as
exactly one token-aligned 32 px square: no resampling by the server, no cell split across
tokens, and a fixed cost of 14 x 21 = 294 image tokens per decision.
"""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw, ImageFont
from tetris import HEIGHT, HIDDEN, SHAPES, WIDTH, Board, Piece, heights

TOKEN = 32  # pixels per visual token edge: 16 px patch x 2 spatial merge
CELL = TOKEN
PANEL = 4  # columns of side panel, in cells
VIEW_SIZE = ((WIDTH + PANEL) * CELL, (HEIGHT + 1) * CELL)  # 448 x 672

COLORS = {
    "I": (0, 200, 220),
    "O": (240, 200, 0),
    "T": (165, 85, 225),
    "S": (70, 195, 90),
    "Z": (230, 65, 75),
    "J": (50, 115, 240),
    "L": (245, 140, 30),
}
BACKGROUND = (10, 13, 18)
WELL = (18, 22, 30)
GRID = (40, 48, 62)
TEXT = (235, 240, 245)
MUTED = (140, 150, 165)
LINE = (255, 214, 64)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _block(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color, outline=None) -> None:
    """A solid block with a darker rim so neighbouring cells stay distinct."""
    rim = max(1, size // 16)
    dark = tuple(int(c * 0.55) for c in color)
    draw.rectangle((x, y, x + size - 1, y + size - 1), fill=dark)
    draw.rectangle((x + rim, y + rim, x + size - 1 - rim, y + size - 1 - rim), fill=color)
    if outline:
        draw.rectangle((x, y, x + size - 1, y + size - 1), outline=outline, width=rim + 1)


def _well(draw: ImageDraw.ImageDraw, ox: int, oy: int, size: int) -> None:
    draw.rectangle((ox, oy, ox + WIDTH * size - 1, oy + HEIGHT * size - 1), fill=WELL)
    for c in range(WIDTH + 1):
        draw.line((ox + c * size, oy, ox + c * size, oy + HEIGHT * size - 1), fill=GRID)
    for r in range(HEIGHT + 1):
        draw.line((ox, oy + r * size, ox + WIDTH * size - 1, oy + r * size), fill=GRID)


def _stack(draw: ImageDraw.ImageDraw, board: Board, ox: int, oy: int, size: int) -> None:
    for y in range(HIDDEN, HIDDEN + HEIGHT):
        for x, kind in enumerate(board[y]):
            if kind:
                _block(draw, ox + x * size, oy + (y - HIDDEN) * size, size, COLORS[kind])


def _piece(draw, piece: Piece, ox: int, oy: int, size: int, outline=None, ghost=False) -> None:
    for x, y in piece.cells():
        if y < HIDDEN:
            continue
        px, py = ox + x * size, oy + (y - HIDDEN) * size
        if ghost:
            draw.rectangle((px + 2, py + 2, px + size - 3, py + size - 3), outline=MUTED, width=2)
        else:
            _block(draw, px, py, size, COLORS[piece.kind], outline)


def _preview(draw, kind: str, ox: int, oy: int, size: int) -> None:
    """Draw a piece in spawn orientation, centred in a 4 x 2 cell box."""
    cells = SHAPES[kind][0]
    xs, ys = [x for x, _ in cells], [y for _, y in cells]
    dx = (4 - (max(xs) - min(xs) + 1)) * size // 2 - min(xs) * size
    dy = (2 - (max(ys) - min(ys) + 1)) * size // 2 - min(ys) * size
    for x, y in cells:
        _block(draw, ox + dx + x * size, oy + dy + y * size, size, COLORS[kind])


def jev_view(board: Board, piece: Piece | None, upcoming: list[str]) -> Image.Image:
    """The screenshot Jev decides from: well, falling piece, column numbers and next queue."""
    image = Image.new("RGB", VIEW_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    _well(draw, 0, 0, CELL)
    _stack(draw, board, 0, 0, CELL)
    if piece:
        _piece(draw, piece, 0, 0, CELL, outline=(255, 255, 255))
    digits = font(20)
    for x in range(WIDTH):
        draw.text(
            (x * CELL + CELL // 2, HEIGHT * CELL + CELL // 2),
            str(x),
            fill=TEXT,
            font=digits,
            anchor="mm",
        )
    left = WIDTH * CELL
    draw.text((left + PANEL * CELL // 2, CELL // 2), "NEXT", fill=TEXT, font=font(20), anchor="mm")
    for i, kind in enumerate(upcoming[:3]):
        _preview(draw, kind, left, CELL * (1 + 3 * i) + CELL // 2, CELL)
    return image


def result_view(board: Board, option, cell: int = CELL) -> Image.Image:
    """The well right after one placement, before completed rows vanish: the placed piece
    is outlined in white and each completed row is framed in yellow."""
    image = Image.new("RGB", (WIDTH * cell, HEIGHT * cell), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _well(draw, 0, 0, cell)
    _stack(draw, board, 0, 0, cell)
    _piece(draw, option.piece, 0, 0, cell, outline=(255, 255, 255))
    for y in option.cleared:
        top = (y - HIDDEN) * cell
        draw.rectangle((0, top, WIDTH * cell - 1, top + cell - 1), outline=LINE, width=3)
    return image


SHEET_CELL = TOKEN // 2  # one 16 px vision patch per cell; 2 x 2 cells share a token
SHEET_PER_ROW = 5
TILE_WIDTH = WIDTH * SHEET_CELL + TOKEN  # 160 px well + 32 px gutter = 6 tokens


def labels(count: int) -> list[str]:
    """Option labels in the order OpenJev assigns them: A..Z, then AA, AB, ..."""
    singles = [chr(65 + i) for i in range(26)]
    doubles = [a + b for a in singles for b in singles]
    return (singles + doubles)[:count]


def outcome_sheet(plans, cell: int = SHEET_CELL) -> Image.Image:
    """One lettered tile per option: the well after both pieces land.

    Tiles show only the rows in use (plus two), so the sheet stays small: a typical five
    option decision costs about 90 image tokens. Cleared rows are reported as +N in the
    tile header; holes stay visible as dark gaps under blocks.
    """
    tallest = max(max(heights(p.board)) for p in plans)
    rows = min(HEIGHT, max(4, tallest + 2))
    rows += rows % 2  # even row count keeps every tile on 32 px token boundaries
    per_row = min(SHEET_PER_ROW, len(plans))
    tile_height = TOKEN + rows * cell
    grid_rows = -(-len(plans) // per_row)
    image = Image.new("RGB", (per_row * TILE_WIDTH, grid_rows * tile_height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    header = font(22)
    top = HIDDEN + HEIGHT - rows
    for i, (plan, label) in enumerate(zip(plans, labels(len(plans)), strict=True)):
        ox = (i % per_row) * TILE_WIDTH + TOKEN // 2
        oy = (i // per_row) * tile_height
        caption = label + (f"  +{plan.lines}" if plan.lines else "")
        draw.text(
            (ox + WIDTH * cell // 2, oy + TOKEN // 2),
            caption,
            fill=LINE if plan.lines else TEXT,
            font=header,
            anchor="mm",
        )
        well_top = oy + TOKEN
        draw.rectangle((ox, well_top, ox + WIDTH * cell - 1, well_top + rows * cell - 1), fill=WELL)
        for y, row in enumerate(plan.board[top:]):
            for x, kind in enumerate(row):
                if kind:
                    _block(draw, ox + x * cell, well_top + y * cell, cell, COLORS[kind])
    return image


def data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def tokens(image: Image.Image) -> int:
    """Visual tokens the backend spends on an image that is already token-aligned."""
    width, height = image.size
    return (width // TOKEN) * (height // TOKEN)
