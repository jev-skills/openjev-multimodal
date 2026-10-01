"""Let a local OpenJev Multimodal model play Tetris and record every decision.

    uv run python examples/tetris/play.py play --seed 7
    uv run python examples/tetris/play.py bench --url http://127.0.0.1:8000 --seeds 7,1,2
    uv run python examples/tetris/play.py ablation --url http://127.0.0.1:8000

`bench` writes one JSON file per model profile under report/runs/. Each game stores the
seed and the chosen key sequences, so the replay, the videos and the report re-simulate it
exactly. Start one profile at a time with `uv run openjev serve --profile ...`.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx
from jev import MODES, Jev, payload
from tetris import Game, frontier, heights, holes

HERE = Path(__file__).resolve().parent
RUNS = HERE / "report" / "runs"
PROFILES = {
    "Qwen/Qwen3.5-0.8B": "fast",
    "Qwen/Qwen3.5-4B": "balanced",
    "Qwen/Qwen3.6-35B-A3B": "quality",
    "Qwen/Qwen3.8-27B": "max",
}


class IllegalKey(RuntimeError):
    """The planner and the engine disagree; never expected."""


def press_all(game: Game, keys: tuple[str, ...]) -> None:
    for key in keys:
        if not game.press(key):
            raise IllegalKey(f"{key!r} had no effect on {game.piece}")


def play(
    jev: Jev, seed: int, mode: str = "vision", max_pieces: int = 100, goal: int = 10, log=print
) -> dict:
    """One game: a decision per two pieces until the piece budget or a top out."""
    game = Game(seed)
    decisions, reached = [], None
    started = time.perf_counter()
    thinking = 0.0
    while not game.over and game.pieces + 2 <= max_pieces:
        decision = jev.decide(game, len(decisions), mode)
        if decision is None:  # every placement tops out before the next piece can enter
            game.over = True
            break
        thinking += decision.client_ms
        press_all(game, decision.plan.first.keys)
        press_all(game, decision.plan.second.keys)
        record = decision.record()
        record["after"] = {
            "pieces": game.pieces,
            "lines": game.lines,
            "clears": game.clears,
            "score": game.score,
            "holes": holes(game.board),
            "height": max(heights(game.board)),
        }
        decisions.append(record)
        if reached is None and game.clears >= goal:
            reached = {
                "decision": len(decisions),
                "pieces": game.pieces,
                "lines": game.lines,
                "score": game.score,
                "holes": holes(game.board),
                "max_holes": max(d["after"]["holes"] for d in decisions),
                "max_height": max(d["after"]["height"] for d in decisions),
                "thinking_ms": round(thinking, 1),
                "wall_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        if log and len(decisions) % 10 == 0:
            log(
                f"  seed {seed} {mode}: {game.pieces} pieces, {game.clears} clears, "
                f"{game.lines} lines, score {game.score}"
            )
    asked = [d for d in decisions if not d["forced"]]
    result = {
        "pieces": game.pieces,
        "lines": game.lines,
        "clears": game.clears,
        "score": game.score,
        "topped_out": game.over,
        "goal": goal,
        "goal_reached": reached is not None,
        "goal_run": reached,
        "decisions": len(decisions),
        "forced": len(decisions) - len(asked),
        "agreement": sum(d["chosen"] == d["reference"] for d in asked) / max(1, len(asked)),
        "mean_regret": statistics.fmean(d["regret"] for d in asked) if asked else 0.0,
        "max_holes": max((d["after"]["holes"] for d in decisions), default=0),
        "final_holes": holes(game.board),
        "max_height": max((d["after"]["height"] for d in decisions), default=0),
        "thinking_ms": round(thinking, 1),
        "wall_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    return {
        "seed": seed,
        "mode": mode,
        "max_pieces": max_pieces,
        "result": result,
        "decisions": decisions,
    }


def dumps(document: dict) -> str:
    """JSON with one line per decision: readable receipts at a third of the indented size."""
    games = []
    for game in document["games"]:
        head = json.dumps({k: v for k, v in game.items() if k != "decisions"})[:-1]
        rows = ",\n".join("   " + json.dumps(d, separators=(",", ":")) for d in game["decisions"])
        games.append(f'  {head}, "decisions": [\n{rows}\n  ]}}')
    head = json.dumps({k: v for k, v in document.items() if k != "games"}, indent=1)[:-2]
    return head + ',\n "games": [\n' + ",\n".join(games) + "\n ]\n}\n"


def machine(build: str | None = None) -> dict:
    """The test machine; `build` is the llama.cpp build the API reports, if any."""

    def run(*command: str) -> str:
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=10)
            return done.stdout + done.stderr  # llama-server prints its version on stderr
        except (OSError, subprocess.SubprocessError):
            return ""

    if build is None:
        llama = run("llama-server", "--version")
        found = next((line.split()[1] for line in llama.splitlines() if "version:" in line), "")
        build = f"b{found}" if found else None
    memory = run("sysctl", "-n", "hw.memsize").strip()
    return {
        "system": f"{platform.system()} {platform.machine()}",
        "chip": run("sysctl", "-n", "machdep.cpu.brand_string").strip(),
        "memory_gb": round(int(memory) / 2**30) if memory.isdigit() else None,
        "llama_cpp": build,
        "python": platform.python_version(),
    }


def describe_server(jev: Jev) -> dict:
    health = jev.health()
    version = jev.http.get(jev.url + "/openapi.json").json()["info"]["version"]
    limits = jev.http.get(jev.url + "/v1/limits").json()
    return {
        "model": health["model"],
        "backend_build": health.get("backend_build"),
        "weights": health.get("weights"),
        "profile": PROFILES.get(health["model"], health["model"]),
        "multimodal": health["multimodal"],
        "openjev": version,
        "image_max_edge": limits["image_max_edge"],
    }


def bench(args) -> None:
    jev = Jev(args.url)
    server = describe_server(jev)
    profile = args.profile or server["profile"]
    print(f"{profile}: {server['model']} at {args.url}", flush=True)
    games = []
    for mode in args.modes.split(","):
        for seed in (int(s) for s in args.seeds.split(",")):
            game = play(jev, seed, mode, args.pieces, args.goal)
            r = game["result"]
            print(
                f"{profile} {mode} seed {seed}: {r['pieces']} pieces, {r['clears']} clears, "
                f"{r['lines']} lines, score {r['score']}, holes max {r['max_holes']}, "
                f"height max {r['max_height']}, topped out {r['topped_out']}",
                flush=True,
            )
            games.append(game)
    RUNS.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else RUNS / f"{profile}.json"
    document = {
        "schema": 1,
        "profile": profile,
        "server": server,
        "machine": machine(server.get("backend_build")),
        "measured": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "games": games,
    }
    out.write_text(dumps(document))
    print(f"wrote {out}")


def simulate(seed: int, choose, rng: random.Random, max_pieces: int, goal: int) -> dict:
    """One game on the same pruned options, with `choose` in place of the model."""
    game = Game(seed)
    most_holes, reached = 0, False
    while not game.over and game.pieces + 2 <= max_pieces:
        options = frontier(game.plans())
        if not options:
            game.over = True
            break
        plan = options[choose(options, rng)]
        press_all(game, plan.first.keys)
        press_all(game, plan.second.keys)
        most_holes = max(most_holes, holes(game.board))
        reached = reached or game.clears >= goal
    return {
        "seed": seed,
        "lines": game.lines,
        "score": game.score,
        "goal_reached": reached,
        "topped_out": game.over,
        "max_holes": most_holes,
    }


BASELINES = {  # policy name: how it picks among the plans the model would see
    "random": lambda options, rng: rng.randrange(len(options)),
    "first": lambda options, rng: 0,
    "reference": lambda options, rng: max(range(len(options)), key=lambda i: options[i].value()),
}


def baseline(args) -> None:
    """What the pruned options achieve without a model: random, leftmost and reference picks."""
    seeds = [int(s) for s in args.seeds.split(",")]
    policies = {}
    for name, choose in BASELINES.items():
        repeats = args.repeats if name == "random" else 1
        games = [
            simulate(seed, choose, random.Random(seed * 1000 + r), args.pieces, args.goal)
            for seed in seeds
            for r in range(repeats)
        ]
        policies[name] = {
            "games": len(games),
            "goal_reached": sum(g["goal_reached"] for g in games),
            "topped_out": sum(g["topped_out"] for g in games),
            "mean_lines": round(statistics.fmean(g["lines"] for g in games), 1),
            "mean_score": round(statistics.fmean(g["score"] for g in games)),
            "best_score": max(g["score"] for g in games),
            "median_max_holes": statistics.median(g["max_holes"] for g in games),
            "runs": games,
        }
        summary = {k: v for k, v in policies[name].items() if k != "runs"}
        print(name, json.dumps(summary), flush=True)
    out = HERE / "report" / "baselines.json"
    document = {"schema": 1, "seeds": seeds, "pieces": args.pieces, "goal": args.goal}
    out.write_text(json.dumps(document | {"policies": policies}, indent=1) + "\n")
    print(f"wrote {out}")


def probe(args) -> None:
    """Time a short run of decisions and save every call: for comparing server setups."""
    jev = Jev(args.url)
    server = describe_server(jev)
    game, calls = Game(args.seed), []
    for number in range(args.decisions):
        decision = jev.decide(game, number, args.mode)
        if decision is None:
            break
        if not decision.forced:
            calls.append(
                {
                    "client_ms": round(decision.client_ms, 1),
                    "timing": decision.timing,
                    "input_tokens": decision.input_tokens,
                }
            )
        press_all(game, decision.plan.first.keys)
        press_all(game, decision.plan.second.keys)
    times = sorted(c["client_ms"] for c in calls)
    result = {
        "schema": 1,
        "name": args.name,
        "server": server,
        "machine": machine(server.get("backend_build")),
        "measured": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "seed": args.seed,
        "mode": args.mode,
        "median_ms": round(statistics.median(times), 1),
        "calls": calls,
    }
    out = HERE / "report" / "probes" / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(f"{args.name}: {len(calls)} calls, median {result['median_ms']:.0f} ms -> {out.name}")


def fixed_states(seeds=(1, 2, 3, 4), per_seed: int = 12) -> list[Game]:
    """Decision states along the reference player's games (at least two options each)."""
    states = []
    for seed in seeds:
        game = Game(seed)
        picked = 0
        while not game.over and picked < per_seed:
            options = frontier(game.plans())
            if not options:
                break
            if len(options) > 1:
                states.append(copy.deepcopy(game))
                picked += 1
            best = max(options, key=lambda p: p.value())
            press_all(game, best.first.keys)
            press_all(game, best.second.keys)
    return states


def ablation(args) -> None:
    """Same states, different presentations: what does Jev need to choose well?"""
    jev = Jev(args.url)
    server = describe_server(jev)
    profile = args.profile or server["profile"]
    states = fixed_states()
    variants = args.variants.split(",")
    results = {}
    for variant in variants:
        mode, _, scale = variant.partition("@")
        rows = []
        for game in states:
            options = frontier(game.plans())
            body, image = payload(game, options, mode)
            if scale:
                body["images"] = [rescaled(body["images"][0], float(scale))]
            started = time.perf_counter()
            response = jev.http.post(jev.url + "/v1/systemone", json=body)
            response.raise_for_status()
            elapsed = (time.perf_counter() - started) * 1000
            chosen = int(response.json()["answers"]["plan"]["choice"])
            values = [p.value() for p in options]
            new = [p.new_holes for p in options]
            rows.append(
                {
                    "agree": chosen == values.index(max(values)),
                    "regret": max(values) - values[chosen],
                    "avoidable_hole": new[chosen] > 0 and min(new) == 0,
                    "client_ms": elapsed,
                    "input_tokens": response.json()["usage"]["input_tokens"],
                }
            )
        results[variant] = {
            "states": len(rows),
            "agreement": sum(r["agree"] for r in rows) / len(rows),
            "mean_regret": statistics.fmean(r["regret"] for r in rows),
            "avoidable_holes": sum(r["avoidable_hole"] for r in rows),
            "hole_traps": sum(
                1 for g in states if len({p.new_holes > 0 for p in frontier(g.plans())}) == 2
            ),
            "median_ms": statistics.median(r["client_ms"] for r in rows),
            "median_input_tokens": statistics.median(r["input_tokens"] for r in rows),
        }
        print(profile, variant, json.dumps(results[variant]), flush=True)
    out = HERE / "report" / "ablation" / f"{profile}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    earlier = json.loads(out.read_text())["results"] if out.exists() else {}
    document = {
        "schema": 1,
        "profile": profile,
        "server": server,
        "machine": machine(server.get("backend_build")),
        "measured": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "results": earlier | results,  # re-running a variant replaces only that variant
    }
    out.write_text(json.dumps(document, indent=1) + "\n")
    print(f"wrote {out}")


def rescaled(url: str, scale: float) -> str:
    """Resample an image data URL to test other resolutions of the same picture."""
    import base64
    import io

    from PIL import Image
    from vision import data_url

    image = Image.open(io.BytesIO(base64.b64decode(url.partition(",")[2])))
    size = (round(image.width * scale), round(image.height * scale))
    return data_url(image.resize(size, Image.Resampling.LANCZOS))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("play", help="play one game and print the moves")
    many = sub.add_parser("bench", help="play several seeds and write report/runs/<profile>.json")
    study = sub.add_parser("ablation", help="compare presentations on fixed decision states")
    timing = sub.add_parser("probe", help="time a few decisions and save every call")
    timing.add_argument("name", help="receipt name: report/probes/<name>.json")
    timing.add_argument("--url", default="http://127.0.0.1:8000")
    timing.add_argument("--seed", type=int, default=7)
    timing.add_argument("--mode", choices=MODES, default="compact")
    timing.add_argument("--decisions", type=int, default=16)
    base = sub.add_parser("baseline", help="play the pruned options without a model")
    base.add_argument("--seeds", default="101,202,303,404,505")
    base.add_argument("--repeats", type=int, default=20, help="random games per seed")
    base.add_argument("--pieces", type=int, default=100)
    base.add_argument("--goal", type=int, default=10)
    for command in (one, many, study):
        command.add_argument("--url", default="http://127.0.0.1:8000")
        command.add_argument("--profile", help="name for the output file (default: from /health)")
    for command in (one, many):
        command.add_argument("--pieces", type=int, default=100, help="piece budget per game")
        command.add_argument("--goal", type=int, default=10, help="clears that count as success")
    one.add_argument("--seed", type=int, default=7)
    one.add_argument("--mode", choices=MODES, default="vision")
    many.add_argument("--seeds", default="7,1,2")
    many.add_argument("--modes", default="vision")
    many.add_argument("--out", help="output path (default: report/runs/<profile>.json)")
    study.add_argument("--variants", default="text,vision,pixels,board,board@0.5,board@2.0")
    args = parser.parse_args()
    try:
        if args.command == "play":
            jev = Jev(args.url)
            game = play(jev, args.seed, args.mode, args.pieces, args.goal)
            for d in game["decisions"]:
                option = next(o for o in d["options"] if o["label"] == d["chosen"])
                print(
                    f"#{d['number']:>2} {d['falling']}+{d['next']} -> {d['chosen']} of "
                    f"{len(d['options'])}: {' '.join(option['keys'][0])} | "
                    f"{' '.join(option['keys'][1])}  ({d['client_ms']:.0f} ms)"
                )
            print(json.dumps(game["result"], indent=2))
        elif args.command == "bench":
            bench(args)
        elif args.command == "baseline":
            baseline(args)
        elif args.command == "probe":
            probe(args)
        else:
            ablation(args)
    except httpx.HTTPError as exc:
        sys.exit(f"Cannot reach OpenJev at {args.url}: {exc}. Start it: uv run openjev serve")


if __name__ == "__main__":
    main()
