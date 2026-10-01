"""Render a recorded game as a short, crisp MP4 in the documentation site's visual language.

    uv run python examples/tetris/video.py --profile balanced --seed 101

Left: the well, replayed key by key from the recording. Right: the OpenJev call behind
each move: the image that was sent, the plans with their measured facts, a timer that runs
for the measured round trip, then the returned probabilities. Think time is real; key
presses, drops and line clears are animated at a fixed pace. H.264 (yuv420p, faststart)
keeps files small and playable in every browser. Needs ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import subprocess
import urllib.request
from functools import cache, lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from replay import Decision, Key, Lock, events
from tetris import HEIGHT, HIDDEN, SHAPES, WIDTH, Board, Piece
from vision import COLORS, TILE_WIDTH, labels, outcome_sheet

HERE = Path(__file__).resolve().parent
SIZE = W, H = 1280, 720
FPS = 30

# Pace of the animation, in milliseconds. Think time comes from the recording.
KEY_MS, LOCK_MS, FLASH_MS, COLLAPSE_MS = 70, 50, 170, 150
ANSWER_MS, SETTLE_MS, FORCED_MS, INTRO_MS, OUTRO_MS = 330, 140, 280, 1100, 3200

# Documentation site palette (site/.vitepress/theme/style.css).
BG = (16, 23, 19)
BG_ALT = (11, 17, 13)
PANEL = (20, 30, 22)
LINE = (43, 56, 46)
LINE_2 = (58, 75, 56)
TEXT_1 = (238, 241, 233)
TEXT_2 = (172, 183, 172)
MUTED = (127, 150, 122)
ACCENT = (180, 247, 132)
ACCENT_DIM = (102, 154, 69)
ACCENT_BG = (30, 44, 31)
TRACK = (37, 51, 34)
INK = (24, 38, 19)
WARN = (242, 160, 123)

CELL = 26
WELL_X, WELL_Y = 72, 100
CARD = (540, 84, 1240, 604)
PAD = 24

FONT_DIR = Path.home() / ".cache" / "openjev-multimodal" / "fonts"
FONT_FILES = {
    "DMSans.ttf": "ofl/dmsans/DMSans%5Bopsz,wght%5D.ttf",
    "SpaceGrotesk.ttf": "ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf",
    "DMMono-Regular.ttf": "ofl/dmmono/DMMono-Regular.ttf",
    "DMMono-Medium.ttf": "ofl/dmmono/DMMono-Medium.ttf",
}


def quantization(profile: str) -> str:
    """Weight format of a built-in OpenJev profile, e.g. Q4_K_M."""
    try:
        from openjev.profiles import PROFILES
    except ImportError:
        return "GGUF"
    weights = PROFILES[profile].weights if profile in PROFILES else ""
    found = re.search(r"(?:UD-)?I?Q\d\w*", weights.removesuffix(".gguf"))
    return found.group(0) if found else "GGUF"


def fetch_fonts() -> None:
    """Cache the site's typefaces (SIL Open Font License) from the Google Fonts repository."""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in FONT_FILES.items():
        target = FONT_DIR / name
        if not target.exists():
            url = "https://github.com/google/fonts/raw/main/" + path
            try:
                urllib.request.urlretrieve(url, target)
            except OSError:
                target.unlink(missing_ok=True)  # fall back to system fonts


@cache
def face(family: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    files = {
        "sans": "DMSans.ttf",
        "display": "SpaceGrotesk.ttf",
        "mono": "DMMono-Medium.ttf" if weight >= 500 else "DMMono-Regular.ttf",
    }
    try:
        font = ImageFont.truetype(str(FONT_DIR / files[family]), size)
        if family == "sans":
            font.set_variation_by_axes([min(max(size, 9), 40), weight])
        elif family == "display":
            font.set_variation_by_axes([weight])
        return font
    except OSError:
        system = (
            "/System/Library/Fonts/SFNSMono.ttf"
            if family == "mono"
            else "/System/Library/Fonts/SFNS.ttf"
        )
        try:
            return ImageFont.truetype(system, size)
        except OSError:
            return ImageFont.load_default(size=size)


def mix(a, b, t: float):
    """Blend colour a towards b by t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def ease_out(t: float) -> float:
    return 1 - (1 - max(0.0, min(1.0, t))) ** 3


def ease_in(t: float) -> float:
    return max(0.0, min(1.0, t)) ** 2


@lru_cache(maxsize=256)
def rounded(size: tuple[int, int], radius: int, fill, outline=None, width: int = 1) -> Image.Image:
    """Anti-aliased rounded rectangle, drawn at 4x and downsampled."""
    s = 4
    w, h = size
    big = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    draw.rounded_rectangle(
        (0, 0, w * s - 1, h * s - 1),
        radius * s,
        fill=fill + (255,) if fill else None,
        outline=outline + (255,) if outline else None,
        width=width * s,
    )
    return big.resize(size, Image.Resampling.LANCZOS)


@lru_cache(maxsize=256)
def icon(name: str, size: int, color) -> Image.Image:
    """Vector key icons (the site's typefaces have no rotate or hard-drop glyphs)."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = color + (255,)
    stroke = max(4, round(s * 0.11))
    mid = s / 2
    if name in ("left", "right"):
        d.line((s * 0.2, mid, s * 0.8, mid), fill=c, width=stroke)
        tip, back = (s * 0.14, s * 0.46) if name == "left" else (s * 0.86, s * 0.54)
        d.polygon([(tip, mid), (back, mid - s * 0.24), (back, mid + s * 0.24)], fill=c)
    elif name in ("cw", "ccw"):
        box = (s * 0.18, s * 0.18, s * 0.82, s * 0.82)
        d.arc(box, -40, 250, fill=c, width=stroke)
        # Arrow head at the top of the circle, pointing in the direction of rotation.
        x, y = mid - s * 0.02, s * 0.18
        d.polygon(
            [(x + s * 0.2, y), (x - s * 0.04, y - s * 0.17), (x - s * 0.04, y + s * 0.17)], fill=c
        )
        if name == "ccw":
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif name == "drop":
        d.line((mid, s * 0.12, mid, s * 0.58), fill=c, width=stroke)
        d.polygon([(mid, s * 0.7), (mid - s * 0.24, s * 0.44), (mid + s * 0.24, s * 0.44)], fill=c)
        d.rounded_rectangle((s * 0.18, s * 0.78, s * 0.82, s * 0.88), s * 0.04, fill=c)
    elif name == "check":
        d.line(
            [(s * 0.2, s * 0.52), (s * 0.42, s * 0.74), (s * 0.82, s * 0.28)],
            fill=c,
            width=stroke,
            joint="curve",
        )
    return img.resize((size, size), Image.Resampling.LANCZOS)


def paste(canvas: Image.Image, overlay: Image.Image, x: int, y: int) -> None:
    canvas.paste(overlay, (round(x), round(y)), overlay)


def text(draw, xy, value, font, fill, anchor="la", spacing: float = 0.0) -> None:
    """Draw text; `spacing` adds letter spacing in pixels (for small caps labels)."""
    if not spacing:
        draw.text(xy, value, font=font, fill=fill, anchor=anchor)
        return
    x, y = xy
    width = sum(font.getlength(ch) for ch in value) + spacing * (len(value) - 1)
    if anchor[0] == "r":
        x -= width
    elif anchor[0] == "m":
        x -= width / 2
    for ch in value:
        draw.text((x, y), ch, font=font, fill=fill, anchor="l" + anchor[1])
        x += font.getlength(ch) + spacing


def block(draw, x: float, y: float, size: int, color, lift: float = 0.0) -> None:
    rim = max(1, size // 14)
    dark = mix(color, (0, 0, 0), 0.42)
    face_color = mix(color, (255, 255, 255), lift)
    draw.rectangle((x, y, x + size - 1, y + size - 1), fill=dark)
    draw.rectangle((x + rim, y + rim, x + size - 1 - rim, y + size - 1 - rim), fill=face_color)
    draw.rectangle(
        (x + rim, y + rim, x + size - 1 - rim, y + rim + max(1, size // 9)),
        fill=mix(face_color, (255, 255, 255), 0.18),
    )


class Scene:
    """Everything one frame shows."""

    def __init__(self, run: dict, document: dict):
        self.run, self.document = run, document
        self.board: Board = [[None] * WIDTH for _ in range(HIDDEN + HEIGHT)]
        self.piece: Piece | None = None
        self.piece_y: float | None = None  # fractional row while dropping
        self.trail_from: float | None = None
        self.flash: tuple[list[int], float] | None = None
        self.collapse: tuple[Board, list[int], float] | None = None
        self.queue: list[str] = []
        self.stats = {"score": 0, "lines": 0, "clears": 0, "pieces": 0}
        self.decision: Decision | None = None
        self.sheet: Image.Image | None = None
        self.thumb: Image.Image | None = None
        self.phase = "idle"  # idle, waiting, answered, forced
        self.elapsed = 0.0
        self.answer = 0.0
        self.keys: list[list[str]] = []
        self.active: tuple[int, int] | None = None
        self.overlay: tuple[str, float] | None = None
        self.count = 0


def background(scene: Scene) -> Image.Image:
    """Static layer: header, frames and labels."""
    image = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(image)
    server = scene.document["server"]
    # Header.
    draw.polygon([(40, 32), (49, 23), (58, 32), (49, 41)], fill=ACCENT)
    draw.ellipse((46, 29, 52, 35), fill=BG)
    title = face("display", 20, 600)
    text(draw, (70, 32), "OpenJev Multimodal", title, TEXT_1, "lm")
    text(
        draw,
        (70 + title.getlength("OpenJev Multimodal") + 10, 33),
        "plays Tetris",
        face("sans", 16, 450),
        TEXT_2,
        "lm",
    )
    profile = scene.document["profile"]
    right = W - 40
    text(draw, (right, 32), "REAL-TIME REPLAY", face("mono", 11), MUTED, "rm", spacing=1.6)
    draw.ellipse((right - 150, 29, right - 144, 35), fill=ACCENT)
    model = server["model"].split("/")[-1] + " · " + quantization(profile)
    seed_text = f"seed {scene.run['seed']}"
    text(draw, (right - 172, 32), seed_text, face("mono", 13), MUTED, "rm")
    x = right - 172 - face("mono", 13).getlength(seed_text) - 22
    text(draw, (x, 32), model, face("mono", 13), TEXT_2, "rm")
    x -= face("mono", 13).getlength(model) + 14
    label = face("sans", 13, 600)
    chip_w = round(label.getlength(profile)) + 22
    paste(image, rounded((chip_w, 26), 13, ACCENT_BG, LINE_2), x - chip_w, 19)
    text(draw, (x - chip_w / 2, 32), profile, label, ACCENT, "mm")
    draw.line((0, 64, W, 64), fill=LINE)
    # Well frame.
    paste(
        image,
        rounded((CELL * WIDTH + 28, CELL * HEIGHT + 28), 14, BG_ALT, LINE),
        WELL_X - 14,
        WELL_Y - 14,
    )
    # Side column labels.
    side = WELL_X + CELL * WIDTH + 36
    text(draw, (side, WELL_Y + 2), "NEXT", face("mono", 11), MUTED, "lt", spacing=1.8)
    for i, name in enumerate(("SCORE", "LINES", "PIECES", "CLEARS")):
        text(draw, (side, 290 + i * 78), name, face("mono", 11), MUTED, "lt", spacing=1.8)
    # Call card.
    x0, y0, x1, y1 = CARD
    paste(image, rounded((x1 - x0, y1 - y0), 14, PANEL, LINE), x0, y0)
    text(draw, (x0 + PAD, y0 + 26), "POST /v1/systemone", face("mono", 14), TEXT_2, "lm")
    pill = "1 OUTPUT TOKEN"
    pill_font = face("mono", 10)
    pill_w = round(pill_font.getlength(pill) + 1.4 * (len(pill) - 1)) + 16
    paste(image, rounded((pill_w, 20), 5, None, (73, 99, 59)), x1 - PAD - pill_w, y0 + 16)
    text(draw, (x1 - PAD - pill_w / 2, y0 + 26), pill, pill_font, ACCENT, "mm", spacing=1.4)
    draw.line((x0 + PAD, y0 + 72, x1 - PAD, y0 + 72), fill=LINE)
    heading = "IMAGE SENT" if scene.run["mode"] in ("vision", "pixels", "board") else "OUTCOMES"
    text(draw, (x0 + PAD, y0 + 90), heading, face("mono", 11), MUTED, "lm", spacing=1.8)
    text(draw, (x0 + PAD, y0 + 262), "PLANS", face("mono", 11), MUTED, "lm", spacing=1.8)
    text(draw, (x1 - PAD, y0 + 262), "PROBABILITY", face("mono", 11), MUTED, "rm", spacing=1.8)
    draw.line((x0 + PAD, y1 - 52, x1 - PAD, y1 - 52), fill=LINE)
    text(draw, (CARD[0], 634), "KEYS", face("mono", 11), MUTED, "lm", spacing=1.8)
    caption = (
        "Recorded local run, replayed in real time: waiting time is the measured API round "
        "trip; key, drop and clear animations are added."
    )
    text(draw, (40, 694), caption, face("sans", 12), MUTED, "lm")
    site = "jev-skills.github.io/openjev-multimodal"
    text(draw, (W - 40, 694), site, face("mono", 12), MUTED, "rm")
    return image


def draw_well(image: Image.Image, draw: ImageDraw.ImageDraw, scene: Scene) -> None:
    for c in range(1, WIDTH):
        x = WELL_X + c * CELL
        draw.line((x, WELL_Y, x, WELL_Y + HEIGHT * CELL - 1), fill=(20, 29, 23))
    for r in range(1, HEIGHT):
        y = WELL_Y + r * CELL
        draw.line((WELL_X, y, WELL_X + WIDTH * CELL - 1, y), fill=(20, 29, 23))
    board = scene.board
    offsets = {}
    if scene.collapse:
        board, full, p = scene.collapse
        shift = ease_out(p)
        for y in range(len(board)):
            below = sum(1 for f in full if f > y)
            offsets[y] = below * shift if y not in full else None
    for y in range(HIDDEN, HIDDEN + HEIGHT):
        row = board[y]
        if scene.collapse and offsets.get(y) is None:
            continue  # cleared rows are gone while the stack settles
        dy = offsets.get(y, 0.0) or 0.0
        lift = 0.0
        if scene.flash and y in scene.flash[0]:
            lift = 0.85 * math.sin(math.pi * min(1.0, scene.flash[1]))
        for x, kind in enumerate(row):
            if kind:
                py = WELL_Y + (y - HIDDEN + dy) * CELL
                if py >= WELL_Y - 1:
                    block(draw, WELL_X + x * CELL, py, CELL, COLORS[kind], lift)
        if lift:
            glow = mix(ACCENT, (255, 255, 255), 0.5)
            top = WELL_Y + (y - HIDDEN) * CELL
            draw.rectangle(
                (WELL_X, top, WELL_X + WIDTH * CELL - 1, top + CELL - 1),
                outline=mix(BG_ALT, glow, lift),
                width=2,
            )
    piece = scene.piece
    if piece is not None:
        dy = 0.0 if scene.piece_y is None else scene.piece_y - piece.y
        if scene.trail_from is not None and scene.piece_y is not None:
            # A short streak behind the falling piece that fades out upwards.
            columns = {}
            for x, y in piece.cells():
                columns[x] = min(columns.get(x, y), y)
            travelled = scene.piece_y - scene.trail_from
            length = min(4.0, travelled)
            for x, y in columns.items():
                head = WELL_Y + (y - HIDDEN + dy) * CELL
                for k in range(8):
                    a = head - length * CELL * (k + 1) / 8
                    b = head - length * CELL * k / 8
                    a = max(WELL_Y, a)
                    if b > a:
                        tone = mix(BG_ALT, COLORS[piece.kind], 0.30 * (1 - k / 8))
                        draw.rectangle(
                            (WELL_X + x * CELL + 8, a, WELL_X + (x + 1) * CELL - 9, b), fill=tone
                        )
        for x, y in piece.cells():
            py = WELL_Y + (y - HIDDEN + dy) * CELL
            if py >= WELL_Y - CELL / 2:
                block(draw, WELL_X + x * CELL, max(WELL_Y, py), CELL, COLORS[piece.kind], 0.08)


def mini_piece(draw, kind: str, x: float, y: float, cell: int, fade: float = 0.0) -> None:
    cells = SHAPES[kind][0]
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    ox = x - (min(xs) + max(xs) + 1) * cell / 2
    oy = y - (min(ys) + max(ys) + 1) * cell / 2
    color = mix(COLORS[kind], PANEL, fade)
    for cx, cy in cells:
        block(draw, ox + cx * cell, oy + cy * cell, cell, color)


def draw_side(draw, scene: Scene) -> None:
    side = WELL_X + CELL * WIDTH + 36
    for i, kind in enumerate(scene.queue[:3]):
        mini_piece(
            draw,
            kind,
            side + 40,
            WELL_Y + 52 + i * 52,
            18 if i == 0 else 14,
            0.0 if i == 0 else 0.35,
        )
    stats = scene.stats
    values = [f"{stats['score']:,}", str(stats["lines"]), str(stats["pieces"])]
    for i, value in enumerate(values):
        text(draw, (side, 306 + i * 78), value, face("display", 32, 500), TEXT_1, "lt")
    goal = scene.run["result"]["goal"]
    clears = min(stats["clears"], goal)
    y = 306 + 3 * 78
    text(
        draw,
        (side, y),
        f"{clears}",
        face("display", 32, 500),
        ACCENT if clears >= goal else TEXT_1,
        "lt",
    )
    width = face("display", 32, 500).getlength(str(clears))
    text(draw, (side + width + 6, y + 30), f"/ {goal}", face("sans", 15), MUTED, "ls")
    bar = (side, y + 48, side + 112, y + 52)
    draw.rounded_rectangle(bar, 2, fill=TRACK)
    if clears:
        draw.rounded_rectangle(
            (bar[0], bar[1], bar[0] + (bar[2] - bar[0]) * clears / goal, bar[3]), 2, fill=ACCENT
        )


def sheet_box(scene: Scene):
    """Where the sent image sits on the card, and its scale."""
    x0, y0, x1, _ = CARD
    box_w, box_h = x1 - x0 - 2 * PAD, 136
    sheet = scene.sheet
    scale = min(box_w / sheet.width, box_h / sheet.height, 1.0)
    return x0 + PAD, y0 + 108, scale


def draw_card(image: Image.Image, draw, scene: Scene) -> None:
    decision = scene.decision
    if decision is None:
        return
    x0, y0, x1, y1 = CARD
    record = decision.record
    options = decision.options
    n = len(options)
    falling, upcoming = record["falling"], record["next"]
    number = f"DECISION {record['number'] + 1:02d}"
    text(draw, (x0 + PAD + 190, y0 + 26), number, face("mono", 11), MUTED, "lm", spacing=1.6)
    subtitle = (
        f"{falling} now, {upcoming} next  ·  {n} plan{'s' if n > 1 else ''} left after pruning"
    )
    text(draw, (x0 + PAD, y0 + 52), subtitle, face("sans", 15, 450), TEXT_1, "lm")
    # Progress sweep while the request is in flight.
    if scene.phase == "waiting":
        span = x1 - x0 - 2 * PAD
        head = (scene.elapsed / 650.0) % 1.0
        a = x0 + PAD + span * max(0.0, head - 0.25)
        b = x0 + PAD + span * head
        draw.line((a, y0 + 72, b, y0 + 72), fill=ACCENT, width=2)
    # Image that was sent.
    info = record["image"]
    if info.get("tokens"):
        meta = f"{info['width']} × {info['height']} px  ·  {info['tokens']} image tokens"
    elif scene.run["mode"] == "compact":
        meta = "no image sent  ·  rules cached"
    else:
        meta = "no image sent"
    text(draw, (x1 - PAD, y0 + 90), meta, face("mono", 11), MUTED, "rm")
    sx, sy, scale = sheet_box(scene)
    paste(image, scene.thumb, sx, sy)
    names = labels(n)
    chosen = names.index(record["chosen"])
    shown = scene.phase in ("answered", "forced")
    if shown:
        per_row = min(5, n)
        grid_rows = -(-n // per_row)
        tile_h = scene.sheet.height / grid_rows
        col, row = chosen % per_row, chosen // per_row
        left = sx + (col * TILE_WIDTH + 8) * scale
        top = sy + row * tile_h * scale
        width = (TILE_WIDTH - 16) * scale
        alpha = ease_out(scene.answer)
        draw.rounded_rectangle(
            (left - 3, top + 2, left + width + 3, top + tile_h * scale - 2),
            6,
            outline=mix(PANEL, ACCENT, alpha),
            width=2,
        )
    # Plans and probabilities.
    top = y0 + 282
    room = (y1 - 64) - top
    row_h = min(30, room / max(n, 1))
    bar_x0, bar_x1 = x0 + 420, x1 - PAD - 70
    for i, (name, option) in enumerate(zip(names, record["options"], strict=True)):
        cy = top + i * row_h + row_h / 2
        is_chosen = shown and i == chosen
        if is_chosen:
            highlight = mix(PANEL, ACCENT_BG, ease_out(scene.answer))
            draw.rounded_rectangle(
                (x0 + PAD - 8, cy - row_h / 2 + 1, x1 - PAD + 8, cy + row_h / 2 - 1),
                7,
                fill=highlight,
            )
        badge_fill = mix(ACCENT_BG, ACCENT, ease_out(scene.answer)) if is_chosen else (28, 42, 32)
        badge_text = INK if is_chosen and scene.answer > 0.5 else TEXT_2
        draw.rounded_rectangle((x0 + PAD, cy - 10, x0 + PAD + 28, cy + 10), 5, fill=badge_fill)
        text(draw, (x0 + PAD + 14, cy), name, face("mono", 12, 500), badge_text, "mm")
        fx = x0 + PAD + 44
        font = face("sans", 14, 450)
        clears = option["clears"]
        part = f"clears {clears}"
        text(draw, (fx, cy), part, font, ACCENT if clears else TEXT_2, "lm")
        fx += font.getlength(part) + 16
        holes = option["new_holes"]
        part = f"new holes {holes}"
        text(draw, (fx, cy), part, font, WARN if holes else TEXT_2, "lm")
        fx += font.getlength(part) + 16
        text(draw, (fx, cy), f"height {option['height']}", font, TEXT_2, "lm")
        draw.rounded_rectangle((bar_x0, cy - 3, bar_x1, cy + 3), 3, fill=TRACK)
        if shown:
            p = option["probability"] * ease_out(scene.answer)
            if p > 0.002:
                end = bar_x0 + (bar_x1 - bar_x0) * p
                draw.rounded_rectangle(
                    (bar_x0, cy - 3, max(bar_x0 + 6, end), cy + 3),
                    3,
                    fill=mix(ACCENT_DIM, ACCENT, p),
                )
            value = f"{100 * p:.1f}%"
            text(
                draw, (x1 - PAD, cy), value, face("mono", 13), TEXT_1 if is_chosen else TEXT_2, "rm"
            )
        else:
            text(draw, (x1 - PAD, cy), "—", face("mono", 13), MUTED, "rm")
        if is_chosen and scene.answer > 0.6:
            paste(image, icon("check", 16, ACCENT), bar_x0 - 26, cy - 8)
    # Footer: timing and usage.
    fy = y1 - 26
    mono, strong = face("mono", 12), face("mono", 12, 500)
    if scene.phase == "forced":
        text(
            draw,
            (x0 + PAD, fy),
            "one plan dominates every other: no call needed",
            mono,
            MUTED,
            "lm",
        )
        return
    parts = []
    if scene.phase == "waiting":
        parts = [("waiting for one token  ", MUTED), (f"{scene.elapsed / 1000:.2f} s", ACCENT)]
    else:
        parts = [
            (f"{record['client_ms'] / 1000:.2f} s", ACCENT),
            (" round trip   ", MUTED),
            (f"{record['server_ms'] / 1000:.2f} s", TEXT_1),
            (" server   ", MUTED),
            (f"{record['input_tokens']}", TEXT_1),
            (" input tokens   ", MUTED),
            (f"{record['confidence']:.2f}", TEXT_1),
            (" confidence", MUTED),
        ]
    fx = x0 + PAD
    for value, color in parts:
        font = strong if color is not MUTED else mono
        text(draw, (fx, fy), value, font, color, "lm")
        fx += font.getlength(value)


def draw_keys(image: Image.Image, draw, scene: Scene) -> None:
    if not scene.keys:
        return
    if scene.phase == "waiting" or (scene.phase == "answered" and scene.answer < 0.5):
        waiting = "the key sequence arrives with the answer"
        text(draw, (CARD[0] + 52, 634), waiting, face("sans", 13), MUTED, "lm")
        return
    x = CARD[0] + 52
    cy = 634
    count = sum(len(keys) for keys in scene.keys)
    room = CARD[2] - x - 2 * 34 - 42 - 10
    step = min(40, room // max(count, 1))
    cap = step - 6
    record = scene.decision.record if scene.decision else None
    kinds = [record["falling"], record["next"]] if record else ["", ""]
    for move, keys in enumerate(scene.keys):
        if move:
            text(draw, (x + 4, cy), "then", face("sans", 13), MUTED, "lm")
            x += 42
        mini_piece(draw, kinds[move], x + 14, cy, 7)
        x += 34
        for index, key in enumerate(keys):
            state = "todo"
            if scene.active is not None:
                am, ai = scene.active
                if (move, index) == (am, ai):
                    state = "active"
                elif (move, index) < (am, ai):
                    state = "done"
            fill, border, color = {
                "todo": ((23, 32, 25), LINE_2, TEXT_2),
                "active": (ACCENT, ACCENT, INK),
                "done": ((28, 42, 32), (40, 56, 42), MUTED),
            }[state]
            paste(image, rounded((cap, 30), 7, fill, border), x, cy - 15)
            paste(image, icon(key, 16, color), x + (cap - 16) / 2, cy - 8)
            x += step
        x += 10


def draw_overlay(image: Image.Image, scene: Scene) -> Image.Image:
    kind, t = scene.overlay
    if kind == "intro":
        fade = 1 - ease_in(max(0.0, (t - 0.55) / 0.45))
        veil = Image.new("RGB", SIZE, BG)
        card = ImageDraw.Draw(veil)
        profile = scene.document["profile"]
        model = scene.document["server"]["model"].split("/")[-1]
        text(
            card,
            (W / 2, H / 2 - 30),
            "OpenJev Multimodal plays Tetris",
            face("display", 40, 500),
            TEXT_1,
            "mm",
        )
        subtitle = f"{profile}  ·  {model}  ·  one Choice token plans two pieces"
        text(card, (W / 2, H / 2 + 22), subtitle, face("sans", 18, 450), TEXT_2, "mm")
        return Image.blend(image, veil, fade)
    # Outro: dim the scene and show the goal summary.
    alpha = ease_out(min(1.0, t / 0.25))
    dim = Image.blend(image, Image.new("RGB", SIZE, BG_ALT), 0.72 * alpha)
    card_w, card_h = 640, 330
    cx, cy = (W - card_w) // 2, (H - card_h) // 2
    panel = rounded((card_w, card_h), 18, PANEL, LINE_2)
    layer = dim.copy()
    paste(layer, panel, cx, cy)
    draw = ImageDraw.Draw(layer)
    result = scene.run["result"]
    goal = result["goal_run"]
    paste(layer, icon("check", 30, ACCENT), cx + 40, cy + 40)
    text(
        draw,
        (cx + 84, cy + 55),
        f"{result['goal']} line clears",
        face("display", 36, 500),
        TEXT_1,
        "lm",
    )
    note = f"goal reached after {goal['pieces']} pieces and {goal['decision']} decisions"
    text(draw, (cx + 42, cy + 100), note, face("sans", 16, 450), TEXT_2, "lm")
    asked = [d for d in scene.run["decisions"][: goal["decision"]] if not d["forced"]]
    median = statistics.median(d["client_ms"] for d in asked) / 1000 if asked else 0.0
    cells = [
        (f"{goal['holes']}", "holes left"),
        (f"{goal['max_height']}", "max stack height"),
        (f"{goal['score']:,}", "score"),
        (f"{median:.2f} s", "median call"),
        (f"{goal['thinking_ms'] / 1000:.1f} s", "total think time"),
        (f"{len(asked)}", "calls to OpenJev"),
    ]
    for i, (value, label) in enumerate(cells):
        gx = cx + 42 + (i % 3) * 196
        gy = cy + 148 + (i // 3) * 74
        text(
            draw,
            (gx, gy),
            value,
            face("display", 28, 500),
            ACCENT if i == 0 and goal["holes"] == 0 else TEXT_1,
            "lt",
        )
        text(draw, (gx, gy + 38), label, face("sans", 13), MUTED, "lt")
    machine = scene.document["machine"]
    model = scene.document["server"]["model"]
    foot = f"{model} · {machine['chip']} · llama.cpp {machine['llama_cpp']}"
    text(draw, (cx + 42, cy + card_h - 28), foot, face("mono", 11), MUTED, "lm")
    return Image.blend(dim, layer, alpha)


def render(scene: Scene, base: Image.Image) -> Image.Image:
    image = base.copy()
    draw = ImageDraw.Draw(image)
    draw_well(image, draw, scene)
    draw_side(draw, scene)
    draw_card(image, draw, scene)
    draw_keys(image, draw, scene)
    if scene.overlay:
        image = draw_overlay(image, scene)
    return image


class Encoder:
    """Frames in, H.264 out, at a constant frame rate."""

    def __init__(self, path: Path, crf: int):
        if not shutil.which("ffmpeg"):
            raise SystemExit("ffmpeg is required: brew install ffmpeg")
        self.clock = 0.0
        self.frames = 0
        self.process = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{W}x{H}",
                "-r",
                str(FPS),
                "-i",
                "-",
                "-c:v",
                "libx264",
                "-preset",
                "veryslow",
                "-tune",
                "animation",
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(path),
            ],
            stdin=subprocess.PIPE,
        )

    def hold(self, frame: Image.Image, ms: float) -> None:
        """Show a frame until the clock has advanced by `ms`."""
        self.clock += ms
        target = round(self.clock * FPS / 1000)
        data = frame.tobytes()
        while self.frames < target:
            self.process.stdin.write(data)
            self.frames += 1

    def animate(self, scene: Scene, base: Image.Image, ms: float, step) -> None:
        """Advance `ms` of animation; `step(t)` updates the scene for t in [0, 1]."""
        start = self.clock
        end = start + ms
        while True:
            frame_time = self.frames * 1000 / FPS
            if frame_time >= end:
                break
            step(0.0 if ms <= 0 else (frame_time - start) / ms)
            self.process.stdin.write(render(scene, base).tobytes())
            self.frames += 1
        self.clock = end
        step(1.0)

    def close(self) -> None:
        self.process.stdin.close()
        if self.process.wait() != 0:
            raise SystemExit("ffmpeg failed")


def make_video(document: dict, run: dict, path: Path, crf: int = 30) -> dict:
    scene = Scene(run, document)
    base = background(scene)
    encoder = Encoder(path, crf)
    stream = list(events(run, until_goal=True))
    poster = None
    first = next(e for e in stream if isinstance(e, Decision))
    scene.piece, scene.queue = first.piece, first.queue

    def intro(t):
        scene.overlay = ("intro", t)

    encoder.animate(scene, base, INTRO_MS, intro)
    scene.overlay = None
    for event in stream:
        if isinstance(event, Decision):
            scene.decision = event
            scene.sheet = outcome_sheet(event.options)
            _, _, scale = sheet_box(scene)
            size = (round(scene.sheet.width * scale), round(scene.sheet.height * scale))
            scene.thumb = scene.sheet.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
            plan = event.options[labels(len(event.options)).index(event.record["chosen"])]
            scene.keys = [list(plan.first.keys), list(plan.second.keys)]
            scene.active = None
            scene.board, scene.piece, scene.queue = event.board, event.piece, event.queue
            if event.record["forced"]:
                scene.phase, scene.answer = "forced", 1.0
                encoder.hold(render(scene, base), FORCED_MS)
                continue
            scene.phase, scene.answer = "waiting", 0.0

            def waiting(t, total=event.record["client_ms"]):
                scene.elapsed = t * total

            encoder.animate(scene, base, event.record["client_ms"], waiting)
            scene.phase = "answered"

            def answered(t):
                scene.answer = t

            encoder.animate(scene, base, ANSWER_MS, answered)
            frame = render(scene, base)
            if poster is None and event.record["number"] >= 5 and len(event.options) >= 3:
                poster = frame
            encoder.hold(frame, SETTLE_MS)
        elif isinstance(event, Key):
            scene.active = (event.move, event.index)
            if event.key != "drop":
                scene.piece = event.after
                encoder.hold(render(scene, base), KEY_MS)
                continue
            distance = event.after.y - event.before.y
            scene.piece = event.after
            scene.trail_from = float(event.before.y)

            def falling(t, a=event.before.y, b=event.after.y):
                scene.piece_y = a + (b - a) * ease_in(t)

            encoder.animate(scene, base, 40 + 7 * distance, falling)
            scene.piece_y = None
        elif isinstance(event, Lock):
            scene.trail_from = None
            scene.piece = None
            scene.board = event.settled
            if event.full:

                def flash(t, full=event.full):
                    scene.flash = (full, t)

                encoder.animate(scene, base, FLASH_MS, flash)
                scene.flash = None

                def collapse(t, board=event.settled, full=event.full):
                    scene.collapse = (board, full, t)

                encoder.animate(scene, base, COLLAPSE_MS, collapse)
                scene.collapse = None
            else:
                encoder.hold(render(scene, base), LOCK_MS)
            scene.board = event.after
            scene.stats = {
                "score": event.stats.score,
                "lines": event.stats.lines,
                "clears": event.stats.clears,
                "pieces": event.stats.pieces,
            }
            scene.piece, scene.queue = event.spawned, event.queue
    scene.active = None

    def outro(t):
        scene.overlay = ("outro", t)

    encoder.animate(scene, base, OUTRO_MS, outro)
    encoder.close()
    return {"frames": encoder.frames, "seconds": encoder.frames / FPS, "poster": poster}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="balanced", help="report/runs/<profile>.json")
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--mode", default="vision")
    parser.add_argument("--crf", type=int, default=30, help="x264 quality: lower is sharper")
    parser.add_argument("--out", type=Path, default=HERE / "report" / "videos")
    args = parser.parse_args()
    fetch_fonts()
    document = json.loads((HERE / "report" / "runs" / f"{args.profile}.json").read_text())
    run = next(g for g in document["games"] if g["seed"] == args.seed and g["mode"] == args.mode)
    if not run["result"]["goal_reached"]:
        raise SystemExit("This game never reached the goal; pick another seed.")
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.profile}.mp4"
    made = make_video(document, run, path, args.crf)
    made["poster"].convert("RGB").save(
        args.out / f"{args.profile}.jpg", quality=86, optimize=True, progressive=True
    )
    size = path.stat().st_size
    print(f"{path}: {made['seconds']:.1f} s, {made['frames']} frames, {size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
