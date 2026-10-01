"""Interleaved latency benchmark for one or more running OpenJev APIs.

uv run python scripts/latency.py --output benchmarks/performance/balanced.json \
    before=http://127.0.0.1:8101 after=http://127.0.0.1:8100

Every trial sends the same fresh payload to each endpoint in rotating order, so load from
other processes affects all of them alike and answers can be compared one to one. A fresh
nonce at the start of the state makes each request cold, like a new user request; the
"repeat" case sends one identical request twice and measures the second. Give every
endpoint its own inference process: two APIs sharing one llama.cpp server would answer the
second request of a trial from the first one's prompt cache. Fixtures are generated
in-process, so the benchmark needs no dataset. With --quiet, a sample is retaken when
another local llama.cpp log grew during it (up to three tries, then kept and flagged).
"""

import argparse
import asyncio
import base64
import io
import json
import platform
import random
import statistics
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

LOGS = Path.home() / ".cache" / "openjev-multimodal"

TICKET = {
    "ticket": {
        "subject": "Charged twice for the annual plan",
        "messages": [
            {
                "from": "customer",
                "text": "I upgraded to the annual plan yesterday and my card was charged twice, "
                "$240 each. The second charge shows as pending. Can you refund the duplicate? "
                "I also can't find the invoice in the dashboard.",
            },
            {
                "from": "agent",
                "text": "I can see two payment attempts. One failed at the processor, but the "
                "bank placed a temporary hold.",
            },
            {
                "from": "customer",
                "text": "The hold is still there today and my rent is due on Friday. "
                "Please escalate if needed.",
            },
        ],
    },
    "account": {"plan": "annual", "tier": "business", "country": "DE", "seats": 12},
}
POLICY = " ".join(
    [
        "The warranty covers manufacturing defects for twenty-four months from delivery, "
        "excluding wear parts, accidental damage and unauthorised repairs."
    ]
    * 45
)
QUESTIONS = {
    "refund": {"type": "noul", "instructions": "Does the customer request a refund?"},
    "team": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
            "billing": "Payments, invoices and refunds",
            "technical": "Software bugs and outages",
            "sales": "Plan changes and quotes",
            "other": None,
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How time-sensitive is it?",
        "criteria": ["Routine", "This week", "Today", "Blocked right now"],
    },
    "mood": {
        "type": "choice",
        "instructions": "What is the customer's mood?",
        "criteria": {"calm": "Calm or neutral", "frustrated": "Frustrated", "angry": "Angry"},
    },
}
FOUR = list(QUESTIONS)


def data_url(image: Image.Image, fmt: str) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **({"quality": 90} if fmt == "JPEG" else {}))
    mime = "jpeg" if fmt == "JPEG" else "png"
    return f"data:image/{mime};base64," + base64.b64encode(buffer.getvalue()).decode()


def screenshot() -> str:
    """A 448 x 672 board-like screenshot: 294 token-aligned 32 px cells."""
    rng = random.Random(3)
    image = Image.new("RGB", (448, 672), (18, 22, 30))
    draw = ImageDraw.Draw(image)
    for row in range(13, 21):
        for col in range(10):
            if rng.random() < 0.7:
                color = rng.choice([(0, 200, 220), (240, 200, 0), (165, 85, 225), (230, 65, 75)])
                box = (col * 32 + 2, row * 32 + 2, col * 32 + 29, row * 32 + 29)
                draw.rectangle(box, fill=color)
    return data_url(image, "PNG")


def photo() -> str:
    """A 2048 x 1536 photo-like JPEG (smooth color field plus sensor-like noise)."""
    rng = random.Random(5)
    small = Image.new("RGB", (64, 48))
    small.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(64 * 48)])
    field = small.resize((2048, 1536), Image.Resampling.BICUBIC)
    noise = Image.effect_noise((2048, 1536), 24).convert("RGB")
    return data_url(Image.blend(field, noise, 0.25), "JPEG")


def payload(state, questions, images=()):
    return {
        "model": "jev-latest",
        "state": state,
        "questions": {k: QUESTIONS[k] for k in questions},
        "images": list(images),
    }


def cases():
    shot, picture = screenshot(), photo()
    return {
        "text_1q": lambda n: payload({"id": n, **TICKET}, ["team"]),
        "text_4q": lambda n: payload({"id": n, **TICKET}, FOUR),
        "long_1q": lambda n: payload({"id": n, "policy": POLICY}, ["refund"]),
        "long_4q": lambda n: payload({"id": n, "policy": POLICY}, FOUR),
        "screenshot_1q": lambda n: payload(f"Screenshot {n}.", ["team"], [shot]),
        "screenshot_4q": lambda n: payload(f"Screenshot {n}.", FOUR, [shot]),
        "photo_1q": lambda n: payload(f"Photo {n}.", ["refund"], [picture]),
        "repeat_1q": lambda n: payload({"id": "fixed", **TICKET}, ["team"]),
    }


def snapshot():
    return {p.name: p.stat().st_size for p in LOGS.glob("backend-*.log")} if LOGS.exists() else {}


async def settle(seconds: float = 3.0, limit: float = 300.0):
    """Wait until no local llama.cpp log has grown for `seconds`."""
    deadline, last, since = time.monotonic() + limit, snapshot(), time.monotonic()
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)
        now = snapshot()
        if now != last:
            last, since = now, time.monotonic()
        elif time.monotonic() - since >= seconds:
            return


async def call(client, url, body):
    start = time.perf_counter()
    response = await client.post(url + "/v1/systemone", json=body)
    elapsed = (time.perf_counter() - start) * 1000
    response.raise_for_status()
    data = response.json()
    decisions, probabilities = {}, {}
    for key, answer in data["answers"].items():
        if answer["type"] == "noul":
            decisions[key] = answer["noul"] > 0.5
            probabilities[key] = [answer["noul"]]
        else:
            decisions[key] = answer.get("choice", round(answer.get("score", 0)))
            probabilities[key] = list(answer["probabilities"].values())
    return {
        "client_ms": round(elapsed, 2),
        "processing_ms": float(response.headers.get("x-openjev-processing-ms", "nan")),
        "timing": data.get("timing"),
        "cached_tokens": int(response.headers.get("x-openjev-cached-tokens", 0)),
        "input_tokens": data["usage"]["input_tokens"],
        "decisions": decisions,
        "probabilities": probabilities,
    }


def median(values: list[float]) -> float | None:
    """Median of the reported values; None when an endpoint reports none (NaN)."""
    present = [v for v in values if v == v]
    return round(statistics.median(present), 1) if present else None


def largest_difference(a: dict, b: dict) -> float:
    """Largest absolute probability difference between two answers to the same payload."""
    return max(abs(x - y) for key in a for x, y in zip(a[key], b[key], strict=True))


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("endpoints", nargs="+", help="name=url pairs; the first is the reference")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=7)
    parser.add_argument(
        "--quiet", action="store_true", help="retake samples that overlap other local inference"
    )
    args = parser.parse_args()
    endpoints = dict(item.split("=", 1) for item in args.endpoints)
    names = list(endpoints)
    report = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": platform.machine(),
        "chip": subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        ).stdout.strip(),
        "trials": args.trials,
        "endpoints": {},
        "cases": {},
    }
    async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
        for name, url in endpoints.items():
            health = (await client.get(url + "/health")).json()
            report["endpoints"][name] = {"url": url, **health}
            for make in (cases()["text_4q"], cases()["screenshot_4q"]):  # warm kernels and caches
                await call(client, url, make(uuid.uuid4().hex))
        for case, make in cases().items():
            rows = {name: [] for name in names}
            for trial in range(args.trials):
                body = make(uuid.uuid4().hex)
                order = names[trial % len(names) :] + names[: trial % len(names)]
                for attempt in range(3):
                    if args.quiet:
                        await settle()
                    before, sample = snapshot(), {}
                    for name in order:
                        if case == "repeat_1q":
                            await call(client, endpoints[name], body)
                        sample[name] = await call(client, endpoints[name], body)
                    clean = snapshot() == before
                    if clean or not args.quiet or attempt == 2:
                        break
                for name in names:
                    rows[name].append({**sample[name], "clean": clean})
            summary = {}
            for name in names:
                own, reference = rows[name], rows[names[0]]
                values = sorted(r["client_ms"] for r in own)
                pairs = list(zip(own, reference, strict=True))
                agree = [a["decisions"] == b["decisions"] for a, b in pairs]
                summary[name] = {
                    "median_ms": round(statistics.median(values), 1),
                    "min_ms": values[0],
                    "max_ms": values[-1],
                    "server_ms": median([r["processing_ms"] for r in own]),
                    "cached_tokens": statistics.median(r["cached_tokens"] for r in own),
                    "input_tokens": own[0]["input_tokens"],
                    "same_decisions_as_reference": sum(agree) / len(agree),
                    "max_probability_difference": max(
                        largest_difference(a["probabilities"], b["probabilities"]) for a, b in pairs
                    ),
                }
            report["cases"][case] = {"summary": summary, "rows": rows}
            medians = "  ".join(f"{n} {summary[n]['median_ms']:8.1f} ms" for n in names)
            print(case.ljust(14), medians, flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print("wrote", args.output)


if __name__ == "__main__":
    asyncio.run(main())
