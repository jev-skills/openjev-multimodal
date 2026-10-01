#!/usr/bin/env python3
"""Check and call a local OpenJev Multimodal service. Python 3.9+, standard library only.

    python3 openjev.py health
    python3 openjev.py ask --state "Checkout screen" --image shot.png \\
        --choice "What payment status is shown?" \\
        --option paid="Payment succeeded" --option failed="Payment failed" --option other
    python3 openjev.py ask --state-file ticket.json --noul "Does the customer ask for a refund?"
    python3 openjev.py ask --state "..." --score "How urgent is this?" \\
        --level "Routine" --level "Needs attention today" --level "Service is down"
    python3 openjev.py image shot.png          # what an image will cost in visual tokens

Environment: OPENJEV_URL (default http://127.0.0.1:8000), OPENJEV_API_KEY (optional Bearer key).
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import struct
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("OPENJEV_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN_EDGE = 32  # Qwen vision: 16 px patches merged 2 x 2 into one token
MAX_EDGE = 1024  # the API downsizes larger images to this longest edge
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
JPEG_FRAMES = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def request(method: str, path: str, body: dict | None = None, timeout: float = 180):
    headers = {"Content-Type": "application/json"}
    if key := os.environ.get("OPENJEV_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read() or b"{}")
            return response.status, payload, dict(response.headers), time.perf_counter() - started
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read() or b"{}")
        except json.JSONDecodeError:
            payload = {}
        return error.code, payload, dict(error.headers), time.perf_counter() - started
    except (urllib.error.URLError, TimeoutError) as error:
        sys.exit(
            f"OpenJev is not reachable at {URL} ({error}). Start it from a clone of "
            "https://github.com/Hand-In/openjev-multimodal with: uv run openjev serve"
        )


def image_size(path: Path) -> tuple[int, int] | None:
    """Width and height of a PNG, JPEG or WebP file, read from its header."""
    data = path.read_bytes()[:65536]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8 ":
            w, h = struct.unpack("<HH", data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X":
            width = int.from_bytes(data[24:27], "little") + 1
            return width, int.from_bytes(data[27:30], "little") + 1
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            length = int.from_bytes(data[i + 2 : i + 4], "big")
            if marker in JPEG_FRAMES:
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            i += 2 + length
    return None


def image_cost(width: int, height: int, budget: int = 512) -> dict:
    """Estimate what the server and the vision encoder will do with an image."""
    scale = min(1.0, MAX_EDGE / max(width, height))
    w, h = round(width * scale), round(height * scale)
    tokens = math.ceil(w / TOKEN_EDGE) * math.ceil(h / TOKEN_EDGE)
    return {
        "sent": [width, height],
        "after_api_resize": [w, h],
        "tokens": tokens,
        "over_budget": tokens > budget,
        "aligned": w % TOKEN_EDGE == 0 and h % TOKEN_EDGE == 0 and scale == 1.0,
    }


def data_url(path: Path) -> str:
    kind = IMAGE_TYPES.get(path.suffix.lower())
    if kind is None:
        sys.exit(f"{path}: use a PNG, JPEG or WebP image")
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def health(_args) -> None:
    status, body, _, _ = request("GET", "/health")
    print(json.dumps(body, indent=2))
    if status != 200:
        sys.exit(1)
    _, limits, _, _ = request("GET", "/v1/limits")
    print(json.dumps(limits, indent=2))


def image(args) -> None:
    for name in args.paths:
        path = Path(name)
        size = image_size(path)
        if size is None:
            print(f"{path}: size unknown (not a PNG, JPEG or WebP header)")
            continue
        cost = image_cost(*size, budget=args.budget)
        note = []
        if cost["after_api_resize"] != cost["sent"]:
            note.append("the API will downsize it")
        if cost["over_budget"]:
            note.append(f"over the {args.budget}-token image budget: the backend will downsample")
        if not cost["aligned"]:
            note.append("render at multiples of 32 px for a crisp, fixed token cost")
        print(
            f"{path}: {size[0]}×{size[1]} px → ~{cost['tokens']} visual tokens"
            + (f" ({'; '.join(note)})" if note else "")
        )


def ask(args) -> None:
    if args.state_file:
        text = Path(args.state_file).read_text()
        try:
            state = json.loads(text)
        except json.JSONDecodeError:
            state = text
    else:
        state = args.state or "See the attached image."
    questions = {}
    if args.noul:
        questions["noul"] = {"type": "noul", "instructions": args.noul}
    if args.choice:
        if len(args.option) < 2:
            sys.exit("--choice needs at least two --option KEY=DESCRIPTION")
        criteria = {}
        for option in args.option:
            key, _, description = option.partition("=")
            criteria[key] = description or None
        questions["choice"] = {"type": "choice", "instructions": args.choice, "criteria": criteria}
    if args.score:
        if len(args.level) < 2:
            sys.exit("--score needs at least two --level, lowest first")
        questions["score"] = {"type": "score", "instructions": args.score, "criteria": args.level}
    if not questions:
        sys.exit("ask needs --noul, --choice or --score")
    body = {"model": "jev-latest", "state": state, "questions": questions}
    if args.image:
        body["images"] = [data_url(Path(p)) for p in args.image]
    status, result, headers, seconds = request("POST", "/v1/systemone", body)
    if status != 200:
        sys.exit(f"HTTP {status}: {json.dumps(result)}")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    for answer in result["answers"].values():
        if answer["type"] == "noul":
            print(f"noul    P(yes) = {answer['noul']:.3f}")
        elif answer["type"] == "choice":
            ranked = sorted(answer["probabilities"].items(), key=lambda kv: -kv[1])
            spread = " · ".join(f"{k} {p:.3f}" for k, p in ranked)
            confidence = answer["confidence"]
            print(f"choice  {answer['choice']}   ({spread})   confidence {confidence:.2f}")
        else:
            top = len(answer["legend"]) - 1
            confidence = answer["confidence"]
            print(f"score   {answer['score']:.2f} on 0–{top}   confidence {confidence:.2f}")
    lower = {k.lower(): v for k, v in headers.items()}
    server = lower.get("x-openjev-elapsed-ms")
    usage = result.get("usage", {})
    print(
        f"{usage.get('input_tokens', '?')} input tokens · {usage.get('output_tokens', '?')} output "
        f"token(s) · {seconds * 1000:.0f} ms round trip"
        + (f" · {float(server):.0f} ms on the server" if server else "")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="backend status and limits")
    look = sub.add_parser("image", help="estimate visual tokens for image files")
    look.add_argument("paths", nargs="+")
    look.add_argument("--budget", type=int, default=512, help="backend image-token budget")
    call = sub.add_parser("ask", help="send one SystemOne request")
    call.add_argument("--state", help="state text")
    call.add_argument("--state-file", help="state from a file (JSON is sent as JSON)")
    call.add_argument("--image", action="append", default=[], help="PNG/JPEG/WebP file; repeatable")
    call.add_argument("--noul", metavar="QUESTION", help="yes/no question")
    call.add_argument("--choice", metavar="QUESTION", help="pick one of the --option values")
    call.add_argument("--option", action="append", default=[], metavar="KEY=DESCRIPTION")
    call.add_argument("--score", metavar="QUESTION", help="position on the --level scale")
    call.add_argument("--level", action="append", default=[], metavar="TEXT", help="lowest first")
    call.add_argument("--json", action="store_true", help="print the raw response")
    args = parser.parse_args()
    {"health": health, "image": image, "ask": ask}[args.command](args)


if __name__ == "__main__":
    main()
