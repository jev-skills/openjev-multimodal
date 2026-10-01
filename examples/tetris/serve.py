"""Serve the browser game and let a local OpenJev Multimodal model play it live.

    uv run python examples/tetris/serve.py                  # http://127.0.0.1:8765
    uv run python examples/tetris/serve.py --jev http://127.0.0.1:8000

GET  /              the game (web/index.html): play, replay recorded runs, or watch Jev live
GET  /api/health    the OpenJev model behind live mode
POST /api/decide    {"board": [[null|"T", ...] x 22], "falling": "T", "queue": ["S", "Z", "I"],
                     "lines": 3, "mode": "vision"}  ->  the decision record, plus the image sent

Binds to localhost only. The OpenJev URL is fixed at startup; requests cannot redirect it.
"""

from __future__ import annotations

import argparse
import json
import threading
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from jev import MODES, Jev
from tetris import KINDS, ROWS, WIDTH, Game, spawn_piece

HERE = Path(__file__).resolve().parent
MAX_BODY = 64 * 1024


def game_from(state: dict) -> Game:
    """Rebuild the part of a game a decision needs, validating every field."""
    board = state.get("board")
    if not (isinstance(board, list) and len(board) == ROWS):
        raise ValueError(f"board must have {ROWS} rows")
    for row in board:
        if not (isinstance(row, list) and len(row) == WIDTH):
            raise ValueError(f"every row needs {WIDTH} cells")
        if any(cell is not None and cell not in KINDS for cell in row):
            raise ValueError("cells are null or one of " + KINDS)
    falling, queue = state.get("falling"), state.get("queue")
    if falling not in KINDS or not isinstance(queue, list) or not queue:
        raise ValueError("falling must be a piece letter and queue a non-empty list")
    if any(kind not in KINDS for kind in queue) or len(queue) > 6:
        raise ValueError("queue holds up to six piece letters")
    lines = state.get("lines", 0)
    if not isinstance(lines, int) or not 0 <= lines < 100_000:
        raise ValueError("lines must be a small non-negative integer")
    game = Game(seed=0)
    game.board = [list(row) for row in board]
    game.piece = spawn_piece(falling)
    game.queue = deque(queue)
    game.lines = lines
    game.over = False
    return game


class Handler(SimpleHTTPRequestHandler):
    jev: Jev
    lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, format, *args):  # keep the console quiet
        pass

    def send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        if self.path == "/api/health":
            try:
                health = self.jev.health()
            except httpx.HTTPError:
                return self.send_json(503, {"error": f"OpenJev is not reachable at {self.jev.url}"})
            return self.send_json(200, {"jev": self.jev.url, **health})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/decide":
            return self.send_json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            return self.send_json(413, {"error": "request body must be under 64 KB"})
        try:
            state = json.loads(self.rfile.read(length))
            mode = state.get("mode", "vision")
            if mode not in MODES:
                raise ValueError(f"mode must be one of {MODES}")
            game = game_from(state)
            with self.lock:  # one decision at a time on the local model
                decision = self.jev.decide(game, int(state.get("number", 0)), mode)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.send_json(422, {"error": str(exc)})
        except (httpx.HTTPError, RuntimeError) as exc:
            return self.send_json(502, {"error": str(exc)})
        if decision is None:
            return self.send_json(200, {"topped_out": True})
        record = decision.record()
        record["image_url"] = decision.image_url
        return self.send_json(200, record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--jev", default="http://127.0.0.1:8000", help="OpenJev Multimodal URL")
    args = parser.parse_args()
    Handler.jev = Jev(args.jev)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Tetris: http://127.0.0.1:{args.port}/  (OpenJev: {args.jev})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
