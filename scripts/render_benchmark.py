"""Render only observed results; never calls an inference endpoint."""

import argparse
import json
import shutil
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from benchmark import TASKS, percentile, wilson

LABELS = {
    "mmlu": "MMLU",
    "gpqa_diamond": "GPQA\nDiamond",
    "arc_easy": "ARC\nEasy",
    "arc_challenge": "ARC\nChallenge",
    "winogrande": "WinoGrande",
    "hellaswag": "HellaSwag",
    "gsm8k_4": "GSM8K\n4 choices",
    "gsm8k_10": "GSM8K\n10 choices",
    "chess": "Chess\n4 moves",
}


def render(directory: Path, samples: int):
    rows = [json.loads(x) for x in (directory / "decisions.jsonl").read_text().splitlines()]
    manifest = json.loads((directory / "manifest.json").read_text())
    report = []
    selected = []
    for task in TASKS:
        subset = [r for r in rows if r["task"] == task][:samples]
        if len(subset) < samples:
            raise ValueError(f"{task}: need {samples} recorded results, have {len(subset)}")
        selected += subset
        correct = sum(r["correct"] for r in subset)
        times = [r["elapsed_ms"] for r in subset]
        report.append(
            {
                "task": task,
                "n": len(subset),
                "correct": correct,
                "accuracy_pct": round(correct / len(subset) * 100, 2),
                "wilson_95_pct": wilson(correct, len(subset)),
                "p50_ms": round(statistics.median(times), 2),
                "p95_ms": round(percentile(times, 0.95), 2),
                "ids": [r["id"] for r in subset],
            }
        )
    result = {
        "metadata": manifest,
        "report_samples_per_task": samples,
        "available_recorded_evaluations": len(rows),
        "selection": (
            "First 20 observations per task in the original seed-42 random sample order. "
            "No selection by correctness. The initial larger run was stopped to limit load; "
            "all completed decisions remain archived. Exploratory subset, not a leaderboard score."
        ),
        "tasks": report,
    }
    (directory / "summary.json").write_text(json.dumps(result, indent=2))
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "text.color": "#e7efdf",
            "font.size": 13,
            "svg.fonttype": "none",
        }
    )
    bg, muted, accent, grid = "#101a14", "#93a58a", "#b4f784", "#354631"
    fig = plt.figure(figsize=(18, 11.2), facecolor=bg)
    fig.text(0.055, 0.927, "OPENJEV  /  MULTIMODAL", color=accent, size=12, weight="bold")
    fig.text(0.055, 0.866, "One token. Nine benchmarks.", size=36, weight="bold")
    fig.text(0.055, 0.819, "Qwen3.6-35B-A3B  ·  UD-Q4_K_XL  ·  Apple M3 Max", color=muted, size=15)
    fig.text(
        0.945,
        0.921,
        "LOCAL INFERENCE\nZERO-SHOT · NO CHAIN OF THOUGHT",
        ha="right",
        va="top",
        color=muted,
        size=10,
        linespacing=1.8,
    )
    ax = fig.add_axes([0.045, 0.215, 0.52, 0.525], projection="polar", facecolor=bg)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    angles = np.linspace(0, 2 * np.pi, len(TASKS), endpoint=False)
    values = [r["accuracy_pct"] for r in report]
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100%"], color="#708567", size=9)
    ax.set_rlabel_position(12)
    ax.set_xticks(angles)
    ax.set_xticklabels([LABELS[t] for t in TASKS], color="#d8e5ce", size=12)
    ax.tick_params(axis="x", pad=17)
    ax.grid(color=grid, alpha=0.72, linewidth=0.8)
    ax.spines["polar"].set_color(grid)
    closed_angles = np.append(angles, angles[0])
    closed_values = values + [values[0]]
    ax.fill(closed_angles, closed_values, color=accent, alpha=0.09)
    ax.plot(closed_angles, closed_values, color=accent, linewidth=2.8)
    ax.scatter(angles, values, color=accent, s=38, edgecolor=bg, linewidth=1.5, zorder=5)
    ax.text(
        0.5,
        -0.11,
        "Accuracy · common 0–100% scale",
        transform=ax.transAxes,
        ha="center",
        color=muted,
        size=11,
    )
    right = fig.add_axes([0.64, 0.225, 0.3, 0.51], facecolor=bg)
    right.set_xlim(0, 100)
    right.set_ylim(-0.7, len(TASKS) - 0.3)
    right.axis("off")
    fig.text(0.64, 0.75, "OBSERVED ACCURACY", color=muted, size=10, weight="bold")
    fig.text(0.945, 0.75, "95% WILSON INTERVAL", ha="right", color=muted, size=9)
    for i, row in enumerate(report):
        y = len(TASKS) - i - 1
        low, high = row["wilson_95_pct"]
        right.text(0, y + 0.23, LABELS[row["task"]].replace("\n", " "), size=12)
        right.text(
            100,
            y + 0.23,
            f"{row['accuracy_pct']:.0f}%  ·  {row['correct']}/{row['n']}",
            ha="right",
            size=11,
            color=accent,
        )
        right.plot([0, 100], [y, y], color="#233420", linewidth=5, solid_capstyle="round")
        right.plot(
            [0, row["accuracy_pct"]],
            [y, y],
            color=accent,
            alpha=0.35,
            linewidth=5,
            solid_capstyle="round",
        )
        right.plot([low, high], [y, y], color="#d5e8c7", linewidth=1)
        right.scatter([row["accuracy_pct"]], [y], color=accent, s=17, zorder=3)
    times = [r["elapsed_ms"] for r in selected]
    fig.text(0.055, 0.095, f"{len(selected)}", color=accent, size=28, weight="bold")
    fig.text(0.055, 0.063, f"evaluations · {samples} per task", color=muted, size=11)
    fig.text(
        0.27, 0.095, f"{statistics.median(times):.0f} ms", color=accent, size=28, weight="bold"
    )
    fig.text(0.27, 0.063, "median HTTP latency · selected cases", color=muted, size=11)
    fig.text(
        0.56,
        0.105,
        "Small-sample, exploratory results. Wide intervals; no competitor scores.",
        color="#bbcbb0",
        size=11,
    )
    fig.text(
        0.56,
        0.073,
        "GSM8K: synthetic numeric distractors. Chess: legal-move selection.",
        color=muted,
        size=10,
    )
    fig.text(
        0.56,
        0.046,
        "Fixed random order · seed 42 · raw receipts and methodology in the repository",
        color=muted,
        size=10,
    )
    artifacts = Path("assets")
    artifacts.mkdir(exist_ok=True)
    fig.savefig(artifacts / "benchmark.png", dpi=100, facecolor=bg)
    fig.savefig(artifacts / "benchmark.svg", facecolor=bg)
    plt.close(fig)
    Path("site/public").mkdir(parents=True, exist_ok=True)
    shutil.copy2(artifacts / "benchmark.png", "site/public/benchmark.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("benchmarks/quality"))
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    render(args.directory, args.samples)
