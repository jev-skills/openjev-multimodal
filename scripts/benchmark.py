"""Reproducible, resumable HTTP benchmark. No proprietary Jev/Terra scores.

uv run --group bench python scripts/benchmark.py --url http://127.0.0.1:8000 --samples 20
Results contain IDs and hashes, never GPQA questions or answer texts.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import random
import statistics
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import chess
import httpx
from datasets import load_dataset
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
TASKS = [
    "mmlu",
    "gpqa_diamond",
    "arc_easy",
    "arc_challenge",
    "winogrande",
    "hellaswag",
    "gsm8k_4",
    "gsm8k_10",
    "chess",
]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def prepare(samples, seed, pinned_sources=None):
    cache = ROOT / ".local" / "benchmark"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"cases-{samples}-{seed}.json"
    if target.exists():
        cached = json.loads(target.read_text())
        if not pinned_sources or cached["sources"] == pinned_sources:
            return cached
    rng = random.Random(seed)
    sources, cases = {}, []
    api = HfApi()

    def dataset(repo, config, split):
        pinned = (pinned_sources or {}).get(repo + "/" + config)
        revision = pinned["revision"] if pinned else api.dataset_info(repo).sha
        sources[repo + "/" + config] = {"revision": revision, "split": split}
        ds = load_dataset(repo, config, split=split, revision=revision)
        indices = rng.sample(range(len(ds)), min(samples, len(ds)))
        return [(i, ds[i]) for i in indices]

    def add(task, idx, state, question, options, correct):
        order = list(range(len(options)))
        rng.shuffle(order)
        keys = [chr(65 + i) for i in range(len(options))]
        payload = {
            "model": "jev-latest",
            "state": state,
            "questions": {
                "answer": {
                    "type": "choice",
                    "instructions": question,
                    "criteria": {k: options[j] for k, j in zip(keys, order, strict=True)},
                }
            },
        }
        cases.append(
            {
                "task": task,
                "id": str(idx),
                "payload": payload,
                "expected": keys[order.index(correct)],
                "input_sha256": digest(payload),
            }
        )

    for idx, row in dataset("cais/mmlu", "all", "test"):
        add(
            "mmlu",
            idx,
            row["question"],
            "Choose the correct answer.",
            row["choices"],
            row["answer"],
        )
    # The authors publish this archive and its password to prevent accidental crawling.
    # Keep its text private, as requested by the dataset authors.
    gpqa_url = "https://raw.githubusercontent.com/idavidrein/gpqa/56686c06f5e19865c153de0fdb11be3890014df7/dataset.zip"
    response = httpx.get(gpqa_url, follow_redirects=True, timeout=120)
    response.raise_for_status()
    expected_hash = (pinned_sources or {}).get("gpqa_diamond", {}).get("archive_sha256")
    if expected_hash and hashlib.sha256(response.content).hexdigest() != expected_hash:
        raise RuntimeError("GPQA archive differs from the published run.")
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    member = next(x for x in archive.namelist() if x.endswith("gpqa_diamond.csv"))
    rows = list(
        csv.DictReader(
            io.StringIO(archive.read(member, pwd=b"deserted-untie-orchid").decode("utf-8-sig"))
        )
    )
    sources["gpqa_diamond"] = {
        "url": gpqa_url,
        "archive_sha256": hashlib.sha256(response.content).hexdigest(),
        "member": member,
        "split": "diamond",
        "total": len(rows),
    }
    for idx in rng.sample(range(len(rows)), min(samples, len(rows))):
        row = rows[idx]
        add(
            "gpqa_diamond",
            idx,
            row["Question"],
            "Choose the correct answer.",
            [row["Correct Answer"]] + [row[f"Incorrect Answer {i}"] for i in range(1, 4)],
            0,
        )
    for config, task in [("ARC-Easy", "arc_easy"), ("ARC-Challenge", "arc_challenge")]:
        for _idx, row in dataset("allenai/ai2_arc", config, "test"):
            add(
                task,
                row["id"],
                row["question"],
                "Choose the correct answer.",
                row["choices"]["text"],
                row["choices"]["label"].index(row["answerKey"]),
            )
    for idx, row in dataset("allenai/winogrande", "winogrande_xl", "validation"):
        add(
            "winogrande",
            idx,
            row["sentence"],
            "Which option correctly fills the blank?",
            [row["option1"], row["option2"]],
            int(row["answer"]) - 1,
        )
    for idx, row in dataset("Rowan/hellaswag", "default", "validation"):
        add(
            "hellaswag",
            idx,
            row["ctx"],
            "Choose the most plausible continuation.",
            row["endings"],
            int(row["label"]),
        )
    for idx, row in dataset("openai/gsm8k", "main", "test"):
        raw = row["answer"].rsplit("####", 1)[1].strip().replace(",", "")
        gold = Decimal(raw)
        pool = []
        candidates = [gold + x for x in [-10, -5, -2, -1, 1, 2, 5, 10]]
        candidates += [gold * 2, gold / 2, gold + 100, gold - 100]
        rng.shuffle(candidates)
        for value in candidates:
            formatted = format(value.normalize(), "f")
            if value != gold and formatted not in pool:
                pool.append(formatted)
        for count in [4, 10]:
            add(
                f"gsm8k_{count}",
                idx,
                row["question"],
                "Choose the correct numeric answer.",
                [format(gold.normalize(), "f")] + pool[: count - 1],
                0,
            )
    sources["chess"] = {
        "generator": "random legal playout, 4-60 plies; one legal UCI move and three illegal moves",
        "python_chess": chess.__version__,
        "seed": seed,
        "meaning": "Move legality, not playing strength or best-move search.",
    }
    for idx in range(samples):
        board = chess.Board()
        for _ in range(rng.randint(4, 60)):
            if board.is_game_over():
                break
            board.push(rng.choice(list(board.legal_moves)))
        if board.is_game_over():
            board = chess.Board()
        legal = rng.choice(list(board.legal_moves))
        illegal = []
        own_squares = [s for s in chess.SQUARES if board.color_at(s) == board.turn]
        while len(illegal) < 3:
            move = chess.Move(rng.choice(own_squares), rng.choice(chess.SQUARES))
            if move not in board.legal_moves and move.from_square != move.to_square:
                if move.uci() not in illegal:
                    illegal.append(move.uci())
        add(
            "chess",
            idx,
            f"Chess position (FEN): {board.fen()}\nBoard:\n{board}",
            "Which UCI move is legal for the side to move?",
            [legal.uci(), *illegal],
            0,
        )
    result = {"sources": sources, "cases": cases, "seed": seed, "samples_per_task": samples}
    target.write_text(json.dumps(result, ensure_ascii=False))
    return result


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))]


def wilson(correct, n):
    p, z = correct / n, 1.96
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [round((center - radius) * 100, 2), round((center + radius) * 100, 2)]


def run(args):
    if args.samples < 1 or args.cooldown < 0:
        raise ValueError("Samples must be positive and cooldown nonnegative.")
    if args.replay_report:
        report = json.loads(Path(args.replay_report).read_text())
        meta = report["metadata"]
        data = prepare(meta["samples_per_task"], meta["seed"], meta["sources"])
        selected_ids = {row["task"]: set(row["ids"]) for row in report["tasks"]}
        data = {
            **data,
            "cases": [
                case
                for case in data["cases"]
                if case["id"] in selected_ids.get(case["task"], set())
            ],
        }
        args.samples = report["report_samples_per_task"]
        args.seed = meta["seed"]
    else:
        data = prepare(args.samples, args.seed)
    print(f"Prepared {len(data['cases'])} cases.", flush=True)
    if args.prepare_only:
        return
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    journal = output / "decisions.jsonl"
    previous = (
        [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
    )
    done = {(r["task"], r["id"]): r for r in previous}
    headers = (
        {"Authorization": f"Bearer {os.environ['OPENJEV_API_KEY']}"}
        if os.getenv("OPENJEV_API_KEY")
        else {}
    )
    with httpx.Client(base_url=args.url, timeout=180, headers=headers, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        model = health.json()["model"]
        metadata = {
            "started_at": datetime.now(UTC).isoformat(),
            "model": model,
            "quantization": args.quantization,
            "hardware": args.hardware,
            "platform": platform.platform(),
            "seed": args.seed,
            "samples_per_task": args.samples,
            "protocol": "Zero-shot, one output token, no chain of thought, shuffled options.",
            "sampling": "Uniform random subset per dataset; fixed seed. Not a full benchmark run.",
            "sources": data["sources"],
            "api_limits": client.get("/v1/limits").json(),
            "git_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
        }
        manifest = output / "manifest.json"
        if manifest.exists():
            old = json.loads(manifest.read_text())
            for key in ["model", "quantization", "seed", "samples_per_task"]:
                if old[key] != metadata[key]:
                    raise RuntimeError(f"Resume mismatch: {key}; choose a new output directory.")
            metadata = old
        else:
            manifest.write_text(json.dumps(metadata, indent=2))
        with journal.open("a") as log:
            for case in data["cases"]:
                key = case["task"], case["id"]
                if key in done:
                    if done[key]["input_sha256"] != case["input_sha256"]:
                        raise RuntimeError("Dataset or prompt changed during resume.")
                    continue
                start = time.perf_counter()
                response = client.post("/v1/systemone", json=case["payload"])
                response.raise_for_status()
                result = response.json()
                answer = result["answers"]["answer"]
                row = {
                    "task": case["task"],
                    "id": case["id"],
                    "input_sha256": case["input_sha256"],
                    "expected": case["expected"],
                    "choice": answer["choice"],
                    "correct": answer["choice"] == case["expected"],
                    "probabilities": answer["probabilities"],
                    "confidence": answer["confidence"],
                    "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                    "usage": result["usage"],
                    "server_timing": response.headers.get("server-timing"),
                    "cached_tokens": int(response.headers.get("x-openjev-cached-tokens", 0)),
                }
                log.write(json.dumps(row) + "\n")
                log.flush()
                done[key] = row
                time.sleep(args.cooldown)
                if len(done) % 20 == 0:
                    print(
                        f"{len(done)}/{len(data['cases'])} · {case['task']} · "
                        f"{row['elapsed_ms']:.0f} ms",
                        flush=True,
                    )
    summaries = []
    for task in TASKS:
        rows = [r for (t, _), r in done.items() if t == task]
        correct = sum(r["correct"] for r in rows)
        times = [r["elapsed_ms"] for r in rows]
        summaries.append(
            {
                "task": task,
                "n": len(rows),
                "correct": correct,
                "accuracy_pct": round(correct / len(rows) * 100, 2),
                "wilson_95_pct": wilson(correct, len(rows)),
                "p50_ms": round(statistics.median(times), 2),
                "p95_ms": round(percentile(times, 0.95), 2),
            }
        )
    result = {
        "metadata": metadata,
        "completed_at": datetime.now(UTC).isoformat(),
        "tasks": summaries,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument(
        "--cooldown",
        type=float,
        default=0.25,
        help="Rest between sequential calls to limit local load",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="benchmarks/local")
    parser.add_argument("--replay-report", help="Replay published IDs and dataset revisions")
    parser.add_argument("--quantization", default="UD-Q4_K_XL")
    parser.add_argument("--hardware", default="Apple M3 Max · 40-core GPU · 128 GB")
    parser.add_argument("--prepare-only", action="store_true")
    run(parser.parse_args())
