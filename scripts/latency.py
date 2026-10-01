"""Interleaved latency benchmark for one or more running OpenJev APIs.

uv run python scripts/latency.py --output benchmarks/performance/balanced.json \
    before=http://127.0.0.1:8101 after=http://127.0.0.1:8100

Every trial sends the same fresh payload to each endpoint in rotating order, so load from
other processes affects all of them alike and answers can be compared one to one. A fresh
nonce at the start of the state makes each request cold, like a new user request; the
"repeat" case sends one identical request twice and measures the second. Give every
endpoint its own inference process: two APIs sharing one llama.cpp server would answer the
second request of a trial from the first one's prompt cache. To keep a large model in
memory only once, point every API at one llama.cpp server started with `--cache-ram 0` and
pass it as --flush: its cached prompt is replaced before each endpoint's request. Fixtures
are generated in-process, so the benchmark needs no dataset. With --quiet, a sample is
retaken when another local llama.cpp log grew during it (up to three tries, then kept and
flagged). --pause idles the GPU before each trial, against thermal throttling.
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

# A browser agent's turn: the page as JSON nodes (about 4k tokens) and twelve questions.
CATEGORIES = (
    "Gizmos Widgets Sprockets Gears Valves Pumps Fasteners Bearings Motors Sensors Cables Switches "
    "Filters Seals Hoses Brackets Clamps Springs Pulleys Belts Chains Couplings Shafts Nozzles"
).split()
FOOTER = (
    "Shipping, Returns, Warranty, Track an order, Payment options, Gift cards, Business "
    "accounts, Tax exemption, Bulk pricing, Quotes, Careers, Press, Sustainability, "
    "Accessibility, Privacy, Terms, Cookies, Sitemap, Contact sales, Support center, "
    "Community, Developer API, Status, Stores, Install guides, Safety data, Recalls, "
    "Affiliates, Blog, Events"
).split(", ")
FIELDS = [
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("street", "Street address"),
    ("city", "City"),
    ("postal_code", "Postal code"),
    ("company", "Company (optional)"),
]
INPUTS = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "phone": "+44 20 7946 0000",
    "street": "12 Analytical Way",
    "city": "London",
    "postal_code": "NW1 6XE",
}


def page_nodes() -> list[dict]:
    nodes = [{"role": "link", "name": "Example Store", "href": "/"}]
    nodes += [{"role": "link", "name": c, "href": f"/c/{c.lower()}"} for c in CATEGORIES]
    nodes += [{"role": "heading", "name": "Checkout", "level": 1}]
    nodes += [
        {"role": "table", "name": "Your cart", "columns": ["Item", "Qty", "Price"], "rows": 6}
    ]
    for field, label in FIELDS:
        nodes.append({"role": "textbox", "name": label, "field": field, "near": "Shipping details"})
    nodes += [
        {"role": "combobox", "name": "Country", "options": ["United Kingdom", "Canada", "France"]}
    ]
    for label in ("I agree to the terms of sale", "Send me product news", "Save this address"):
        nodes.append({"role": "checkbox", "name": label, "checked": False})
    for label in ("Place order", "Save cart for later", "Apply coupon"):
        nodes.append({"role": "button", "name": label})
    for i in range(40):
        product = f"{CATEGORIES[i % len(CATEGORIES)][:-1]} {100 + i * 7} · ${4.5 + i * 3.25:.2f}"
        near = "Recommended for you"
        nodes.append(
            {
                "role": "link",
                "name": product,
                "href": f"/p/{1000 + i}",
                "near": near,
                "offscreen": True,
            }
        )
    nodes += [
        {"role": "link", "name": f, "href": f"/help/{i}", "offscreen": True}
        for i, f in enumerate(FOOTER)
    ]
    return [{"ref": f"e{i + 1}", **node} for i, node in enumerate(nodes)]


NODES = page_nodes()


def page(nonce: str, history: bool = True, filled: bool = False) -> dict:
    """The page; `filled` types into the Email field, a change in the middle of the nodes."""
    nodes = [{**n, "value": INPUTS["email"]} if filled and n["ref"] == "e30" else n for n in NODES]
    view = {
        "id": nonce,
        "page": {"url": "https://store.example/checkout", "title": "Checkout", "nodes": nodes},
    }
    if history:
        view["recent"] = [{"did": 'click "Checkout"', "ok": True, "pageChanged": True}]
    view["task"] = {"goal": "Fill in the shipping details and place the order", "inputs": INPUTS}
    return view


def page_questions() -> dict:
    links = [n for n in NODES if n["role"] in ("link", "button")][:30]
    step = {f"click:{n['ref']}": f'Click {n["role"]} "{n["name"]}"' for n in links}
    step |= {
        "fill": "Type the task inputs into the form fields",
        "done": "The goal is already reached",
        "ask": "None of these: ask for help",
    }
    inputs = {f"in:{k}": f'The task input "{k}" ({v})' for k, v in INPUTS.items()} | {
        "none": "No task input"
    }
    questions = {
        "next": {
            "type": "choice",
            "instructions": "Which single step moves the task forward?",
            "criteria": step,
        },
        "done": {"type": "noul", "instructions": "Does the page show the goal accomplished?"},
        "blocked": {
            "type": "noul",
            "instructions": "Does an obstacle such as a CAPTCHA or an error stop the task?",
        },
        "loading": {"type": "noul", "instructions": "Is the page still loading?"},
        "expect": {
            "type": "choice",
            "instructions": "What should the chosen step change?",
            "criteria": {
                "same": "Nothing visible",
                "update": "Part of the page",
                "dialog": "A dialog opens",
                "navigate": "A new page loads",
            },
        },
        "after": {
            "type": "choice",
            "instructions": "After filling, what should happen?",
            "criteria": {
                "place": 'Click "Place order"',
                "save": 'Click "Save cart for later"',
                "nothing": "Nothing yet",
            },
        },
    }
    for node in [n for n in NODES if n["role"] == "textbox"][:6]:
        questions[f"field:{node['ref']}"] = {
            "type": "choice",
            "instructions": f'Which task input belongs in the textbox "{node["name"]}"?',
            "criteria": inputs,
        }
    return questions


PAGE_QUESTIONS = page_questions()


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
        "page_12q": lambda n: {
            "model": "jev-latest",
            "state": page(n),
            "questions": PAGE_QUESTIONS,
        },
        # after page_12q: the same page without its history, one question (an extraction)
        "page_followup": lambda n: {
            "model": "jev-latest",
            "state": page(n, history=False),
            "questions": {"email": PAGE_QUESTIONS["field:e30"]},
        },
        # after page_12q: the identical state with a new question
        "page_again": lambda n: {
            "model": "jev-latest",
            "state": page(n),
            "questions": {"email": PAGE_QUESTIONS["field:e30"]},
        },
        # after page_12q: the next turn, after typing into the Email field
        "page_filled": lambda n: {
            "model": "jev-latest",
            "state": page(n, filled=True),
            "questions": PAGE_QUESTIONS,
        },
    }


def preludes():
    """Untimed requests sent just before a timed one, with the same nonce."""
    made = cases()
    return {
        "repeat_1q": made["repeat_1q"],
        "page_followup": made["page_12q"],
        "page_again": made["page_12q"],
        "page_filled": made["page_12q"],
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


async def flush(client, url):
    """Replace a shared llama.cpp server's cached prompt, so the next request starts cold."""
    response = await client.post(url + "/completion", json={"prompt": "Flush.", "n_predict": 1})
    response.raise_for_status()


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
    parser.add_argument(
        "--flush", metavar="URL", help="the llama.cpp server all endpoints share (--cache-ram 0)"
    )
    parser.add_argument("--pause", type=float, default=0, help="seconds of idle before each trial")
    parser.add_argument("--cases", help="comma-separated case names to run (default: all)")
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
        "shared_backend": args.flush,
        "pause_s": args.pause,
        "endpoints": {},
        "cases": {},
    }
    async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
        for name, url in endpoints.items():
            health = (await client.get(url + "/health")).json()
            report["endpoints"][name] = {"url": url, **health}
            for make in (cases()["text_4q"], cases()["screenshot_4q"]):  # warm kernels and caches
                await call(client, url, make(uuid.uuid4().hex))
        preface = preludes()
        made = cases()
        chosen = args.cases.split(",") if args.cases else list(made)
        for case, make in [(name, made[name]) for name in chosen]:
            rows = {name: [] for name in names}
            for trial in range(args.trials):
                nonce = uuid.uuid4().hex
                body = make(nonce)
                order = names[trial % len(names) :] + names[: trial % len(names)]
                await asyncio.sleep(args.pause)
                for attempt in range(3):
                    if args.quiet:
                        await settle()
                    before, sample = snapshot(), {}
                    for name in order:
                        if args.flush:
                            await flush(client, args.flush)
                        if case in preface:
                            await call(client, endpoints[name], preface[case](nonce))
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
