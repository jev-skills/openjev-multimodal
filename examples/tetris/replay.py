"""Re-simulate a recorded game, key by key, for the videos and the web replay.

A run stores only the seed and the chosen plans. Replaying them through the engine
reproduces every intermediate state, and every decision is checked against the recording:
the rebuilt option list must offer the same keys under the same label.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tetris import Board, Game, Piece, Plan, dropped, frontier, heights, holes
from vision import labels


class ReplayMismatch(RuntimeError):
    """The engine no longer reproduces the recording."""


@dataclass
class Stats:
    score: int = 0
    lines: int = 0
    clears: int = 0
    pieces: int = 0
    holes: int = 0
    height: int = 0


@dataclass
class Decision:
    record: dict
    options: list[Plan]
    board: Board
    piece: Piece
    queue: list[str]
    stats: Stats


@dataclass
class Key:
    key: str
    before: Piece
    after: Piece
    move: int  # 0 = falling piece, 1 = next piece
    index: int  # position of the key in its move


@dataclass
class Lock:
    settled: Board  # the well with the piece written in, before full rows vanish
    full: list[int]
    after: Board
    stats: Stats
    spawned: Piece | None
    queue: list[str] = field(default_factory=list)


def stats(game: Game) -> Stats:
    return Stats(
        game.score,
        game.lines,
        game.clears,
        game.pieces,
        holes(game.board),
        max(heights(game.board)),
    )


def events(run: dict, until_goal: bool = True):
    """Yield Decision, Key and Lock events for one recorded game."""
    game = Game(run["seed"])
    goal = run["result"]["goal"]
    for record in run["decisions"]:
        options = frontier(game.plans())
        names = labels(len(options))
        if record["chosen"] not in names:
            raise ReplayMismatch(f"decision {record['number']}: no option {record['chosen']}")
        plan = options[names.index(record["chosen"])]
        wanted = next(o for o in record["options"] if o["label"] == record["chosen"])["keys"]
        if [list(plan.first.keys), list(plan.second.keys)] != wanted:
            raise ReplayMismatch(f"decision {record['number']}: keys differ from the recording")
        yield Decision(
            record,
            options,
            [row[:] for row in game.board],
            game.piece,
            list(game.queue),
            stats(game),
        )
        for move, keys in enumerate(plan.keys):
            for index, key in enumerate(keys):
                before = game.piece
                after = dropped(game.board, before) if key == "drop" else None
                if key == "drop":
                    settled = [row[:] for row in game.board]
                    for x, y in after.cells():
                        settled[y][x] = after.kind
                    full = [y for y, row in enumerate(settled) if all(row)]
                if not game.press(key):
                    raise ReplayMismatch(f"decision {record['number']}: {key!r} had no effect")
                if key != "drop":
                    yield Key(key, before, game.piece, move, index)
                    continue
                yield Key(key, before, after, move, index)
                yield Lock(
                    settled,
                    full,
                    [row[:] for row in game.board],
                    stats(game),
                    None if game.over else game.piece,
                    list(game.queue),
                )
        if until_goal and game.clears >= goal:
            return
    if game.score != run["result"]["score"] and not until_goal:
        raise ReplayMismatch("final score differs from the recording")
