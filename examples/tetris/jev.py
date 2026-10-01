"""One Jev Choice decides the next two Tetris moves.

Code owns the rules. It enumerates every legal plan for the falling piece and the next
piece (rotate, shift, hard drop), keeps the plans that no other plan matches or beats on
every measured fact, and presses the keys. Jev owns the judgment. It reads each plan's key
sequence and measured result, looks at the lettered outcome sheet, and selects one plan
with a single output token.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
from tetris import Game, Plan, frontier
from vision import data_url, jev_view, labels, outcome_sheet, tokens

MODES = ("vision", "text", "board", "pixels")  # pixels: outcome sheet, no measured facts

INSTRUCTIONS = {
    "task": "Choose the plan to play: the keys for the falling piece, then for the next piece.",
    "goal": "Clear lines and keep the well healthy for the pieces that follow.",
    "priorities": [
        "Complete rows whenever possible; more rows at once is better.",
        "Do not cover empty cells: new holes are the most expensive mistake.",
        "Keep the stack low and its surface even, so the next pieces fit.",
    ],
    "fields": {
        "cols": "columns the piece occupies after the drop",
        "clears": "rows completed by the two moves",
        "new holes": "empty cells the two moves seal under blocks",
        "height": "tallest column afterwards, in rows",
    },
}
SHEET_NOTE = (
    "The image has one tile per option, lettered like the options: the well after both "
    "pieces land. +N marks rows cleared; dark gaps under blocks are holes."
)
BOARD_NOTE = "The image shows the well, the falling piece outlined in white and the next queue."

KEY_WORDS = {"left": "left", "right": "right", "cw": "rotate", "ccw": "rotate-back", "drop": "drop"}


def keys_text(keys: tuple[str, ...]) -> str:
    return " ".join(KEY_WORDS[k] for k in keys)


def describe(plan: Plan, falling: str, upcoming: str, facts: bool = True) -> str:
    first, second = plan.first, plan.second
    (a, b), (c, d) = first.columns, second.columns
    moves = (
        f"{falling}: {keys_text(first.keys)} → cols {a}-{b}; "
        f"then {upcoming}: {keys_text(second.keys)} → cols {c}-{d}"
    )
    if not facts:
        return moves
    return (
        f"{moves}. Result: clears {plan.lines}, new holes {plan.new_holes}, height {second.height}"
    )


def payload(game: Game, options: list[Plan], mode: str = "vision") -> tuple[dict, dict]:
    """The SystemOne request for one decision, plus facts about the image that was sent."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    falling, upcoming = game.piece.kind, game.queue[0]
    facts = mode != "pixels"
    instructions = dict(INSTRUCTIONS)
    if not facts:
        instructions["fields"] = {"cols": INSTRUCTIONS["fields"]["cols"]}
    body = {
        "model": "jev-latest",
        "state": {
            "game": "Tetris well: 10 columns (0-9, left to right) x 20 rows",
            "falling": falling,
            "next": list(game.queue)[:3],
            "lines_cleared": game.lines,
        },
        "questions": {
            "plan": {
                "type": "choice",
                "instructions": instructions,
                "criteria": {
                    str(i): describe(plan, falling, upcoming, facts)
                    for i, plan in enumerate(options)
                },
            }
        },
    }
    image = None
    if mode in ("vision", "pixels"):
        image = outcome_sheet(options)
        instructions["image"] = SHEET_NOTE
    elif mode == "board":
        image = jev_view(game.board, game.piece, list(game.queue))
        instructions["image"] = BOARD_NOTE
    sent = {"width": 0, "height": 0, "tokens": 0}
    if image is not None:
        body["images"] = [data_url(image)]
        sent = {"width": image.width, "height": image.height, "tokens": tokens(image)}
    return body, sent


@dataclass
class Decision:
    """Everything about one decision that the report and the replay need."""

    number: int
    pieces: int
    falling: str
    upcoming: str
    options: list[Plan]
    chosen: int
    probabilities: list[float]
    confidence: float
    plan_ms: float = 0.0
    client_ms: float = 0.0
    server_ms: float = 0.0
    timing: dict[str, float] = field(default_factory=dict)
    input_tokens: int = 0
    image: dict = field(default_factory=dict)
    image_url: str | None = None  # the exact image sent; kept out of record() to keep runs small

    @property
    def forced(self) -> bool:
        return len(self.options) == 1

    @property
    def plan(self) -> Plan:
        return self.options[self.chosen]

    @property
    def reference(self) -> int:
        values = [p.value() for p in self.options]
        return max(range(len(values)), key=values.__getitem__)

    @property
    def regret(self) -> float:
        return self.options[self.reference].value() - self.plan.value()

    def record(self) -> dict:
        names = labels(len(self.options))
        return {
            "number": self.number,
            "pieces": self.pieces,
            "falling": self.falling,
            "next": self.upcoming,
            "forced": self.forced,
            "chosen": names[self.chosen],
            "reference": names[self.reference],
            "regret": round(self.regret, 4),
            "confidence": round(self.confidence, 4),
            "plan_ms": round(self.plan_ms, 1),
            "client_ms": round(self.client_ms, 1),
            "server_ms": round(self.server_ms, 1),
            "timing": self.timing,
            "input_tokens": self.input_tokens,
            "image": self.image,
            "options": [
                {
                    "label": name,
                    "keys": [list(plan.first.keys), list(plan.second.keys)],
                    "cols": [list(plan.first.columns), list(plan.second.columns)],
                    "clears": plan.lines,
                    "new_holes": plan.new_holes,
                    "height": plan.second.height,
                    "aggregate": plan.second.aggregate,
                    "bumpiness": plan.second.bumpiness,
                    "probability": round(p, 5),
                    "value": round(plan.value(), 4),
                }
                for name, plan, p in zip(names, self.options, self.probabilities, strict=True)
            ],
        }


class Jev:
    """Minimal client for a local OpenJev Multimodal endpoint."""

    def __init__(self, url: str = "http://127.0.0.1:8000", timeout: float = 120):
        self.url = url.rstrip("/")
        self.http = httpx.Client(timeout=timeout, trust_env=False)

    def health(self) -> dict:
        response = self.http.get(self.url + "/health")
        response.raise_for_status()
        return response.json()

    def decide(self, game: Game, number: int = 0, mode: str = "vision") -> Decision | None:
        """Ask for the next plan. None means no plan exists: the well is topping out."""
        planning = time.perf_counter()
        options = frontier(game.plans())
        if not options:
            return None
        common = dict(
            number=number,
            pieces=game.pieces,
            falling=game.piece.kind,
            upcoming=game.queue[0],
            options=options,
        )
        if len(options) == 1:  # a Choice needs two options; nothing to decide
            plan_ms = (time.perf_counter() - planning) * 1000
            return Decision(
                **common, chosen=0, probabilities=[1.0], confidence=1.0, plan_ms=plan_ms
            )
        body, image = payload(game, options, mode)
        started = time.perf_counter()
        plan_ms = (started - planning) * 1000
        response = self.http.post(self.url + "/v1/systemone", json=body)
        client_ms = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            raise RuntimeError(f"OpenJev returned {response.status_code}: {response.text[:300]}")
        result = response.json()
        answer = result["answers"]["plan"]
        return Decision(
            **common,
            chosen=int(answer["choice"]),
            probabilities=[answer["probabilities"][str(i)] for i in range(len(options))],
            confidence=answer["confidence"],
            plan_ms=plan_ms,
            client_ms=client_ms,
            server_ms=float(response.headers.get("x-openjev-elapsed-ms", "nan")),
            timing=server_timing(response.headers.get("server-timing", "")),
            input_tokens=result["usage"]["input_tokens"],
            image=image,
            image_url=body.get("images", [None])[0],
        )


def server_timing(header: str) -> dict[str, float]:
    """Parse `prepare;dur=1.2, queue;dur=0.1, inference;dur=300` into milliseconds."""
    result = {}
    for part in header.split(","):
        name, _, duration = part.strip().partition(";dur=")
        if name and duration:
            result[name] = float(duration)
    return result
