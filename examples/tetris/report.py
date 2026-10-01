"""Build the Tetris test report from the recorded runs.

    uv run python examples/tetris/report.py

Reads report/runs/*.json, report/ablation/*.json and report/baselines.json and writes
report/summary.json, the SVG figures, report/README.md (+ zh-CN) and the visual
report/index.html. No inference happens here: every number comes from the recordings.
"""

from __future__ import annotations

import html
import json
import math
import statistics
from pathlib import Path

import pages

HERE = Path(__file__).resolve().parent
REPORT = HERE / "report"
PROFILES = pages.PROFILES
MODES = pages.MODES
VARIANTS = tuple((key, en, zh) for key, (en, zh) in pages.VARIANT_NAMES.items())

# Chart tokens: the documentation site's dark surface, brand accent and a de-emphasis
# gray (emphasis pair: CVD ΔE 27.5, contrast 13.5:1 and 5.3:1 on the surface).
SURFACE, BORDER, GRID, AXIS = "#141e16", "#2b382e", "#223025", "#3a4b38"
INK_1, INK_2, MUTED = "#eef1e9", "#acb7ac", "#7f967a"
ACCENT, GRAY, SKY = "#b4f784", "#7f967a", "#7cc4ff"
SANS = "'DM Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
DISPLAY = "'Space Grotesk', 'DM Sans', system-ui, sans-serif"
MONO = "'DM Mono', ui-monospace, 'SF Mono', Menlo, monospace"


def load(kind: str) -> dict[str, dict]:
    return {p: json.loads((REPORT / kind / f"{p}.json").read_text()) for p in PROFILES}


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(document: dict) -> dict:
    """Aggregate one profile's games per mode."""
    result = {}
    for mode in MODES:
        games = [g for g in document["games"] if g["mode"] == mode]
        if not games:
            continue
        calls = [d for g in games for d in g["decisions"] if not d["forced"]]
        latency = [d["client_ms"] for d in calls]
        goals = [g["result"]["goal_run"] for g in games if g["result"]["goal_reached"]]
        result[mode] = {
            "games": len(games),
            "seeds": [g["seed"] for g in games],
            "goal_reached": len(goals),
            "clean_goal": sum(1 for goal in goals if goal["holes"] == 0),
            "topped_out": sum(g["result"]["topped_out"] for g in games),
            "pieces_to_goal": [goal["pieces"] for goal in goals],
            "think_to_goal_s": [round(goal["thinking_ms"] / 1000, 2) for goal in goals],
            "score": [g["result"]["score"] for g in games],
            "lines": [g["result"]["lines"] for g in games],
            "clears": [g["result"]["clears"] for g in games],
            "pieces": [g["result"]["pieces"] for g in games],
            "max_holes": [g["result"]["max_holes"] for g in games],
            "max_height": [g["result"]["max_height"] for g in games],
            "agreement": round(statistics.fmean(g["result"]["agreement"] for g in games), 3),
            "mean_regret": round(statistics.fmean(g["result"]["mean_regret"] for g in games), 3),
            "decisions": sum(g["result"]["decisions"] for g in games),
            "calls": len(calls),
            "forced": sum(g["result"]["forced"] for g in games),
            "latency_ms": {
                "median": round(statistics.median(latency), 1),
                "p90": round(quantile(latency, 0.9), 1),
                "min": round(min(latency), 1),
                "max": round(max(latency), 1),
            },
            "server_ms_median": round(statistics.median(d["server_ms"] for d in calls), 1),
            "plan_ms_median": round(
                statistics.median(d["plan_ms"] for g in games for d in g["decisions"]), 1
            ),
            "input_tokens_median": statistics.median(d["input_tokens"] for d in calls),
            "image_tokens_median": statistics.median(d["image"].get("tokens", 0) for d in calls),
            "options_median": statistics.median(
                len(d["options"]) for g in games for d in g["decisions"]
            ),
        }
    return result


def build_summary(runs: dict, ablation: dict, baselines: dict) -> dict:
    first = runs["balanced"]
    return {
        "schema": 1,
        "measured": {p: runs[p]["measured"] for p in PROFILES},
        "machine": first["machine"],
        "llama_cpp": {p: builds(runs[p]) for p in PROFILES},
        "openjev": first["server"]["openjev"],
        "protocol": {
            "seeds": [101, 202, 303, 404, 505],
            "pieces_per_game": 100,
            "goal": "10 line clears",
            "decision": "one Choice question per two pieces (falling + next)",
            "image": "outcome sheet: one tile per plan, 16 px per cell (one vision patch)",
        },
        "profiles": {
            p: {
                "model": runs[p]["server"]["model"],
                "modes": summarize(runs[p]),
                "ablation": ablation[p]["results"],
            }
            for p in PROFILES
        },
        "baselines": {
            name: {k: v for k, v in policy.items() if k != "runs"}
            for name, policy in baselines["policies"].items()
        },
    }


def builds(document: dict) -> dict[str, str]:
    """llama.cpp build per prompt mode: later runs merged into a file keep their own."""
    result = {mode: document["machine"]["llama_cpp"] for mode in MODES}
    for extra in document.get("extra_runs", []):
        for mode in extra["modes"]:
            result[mode] = extra["machine"]["llama_cpp"]
    return {
        mode: build
        for mode, build in result.items()
        if any(g["mode"] == mode for g in document["games"])
    }


# --------------------------------------------------------------------------- SVG


class Svg:
    def __init__(self, width: int, height: int, title: str, subtitle: str, label: str):
        self.width, self.height = width, height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" aria-labelledby="t d">',
            f'<title id="t">{html.escape(title)}</title>',
            f'<desc id="d">{html.escape(label)}</desc>',
            f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" '
            f'fill="{SURFACE}" stroke="{BORDER}"/>',
        ]
        self.text(32, 44, title, 20, INK_1, family=DISPLAY, weight=500)
        self.text(32, 68, subtitle, 13, INK_2)

    def text(self, x, y, value, size=12, fill=INK_2, anchor="start", family=SANS, weight=400):
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">'
            f"{html.escape(str(value))}</text>"
        )

    def line(self, x1, y1, x2, y2, stroke=GRID, width=1, cap="butt"):
        self.parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="{cap}"/>'
        )

    def dot(self, x, y, r, fill, opacity=1.0, tip="", stroke=None):
        ring = f' stroke="{stroke}" stroke-width="2"' if stroke else ""
        body = f"<title>{html.escape(tip)}</title>" if tip else ""
        self.parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" '
            f'fill-opacity="{opacity}"{ring}>{body}</circle>'
        )

    def bar(self, x, y, width, height, fill, tip=""):
        """Horizontal bar: square at the baseline, 4 px rounded data end."""
        r = min(4, height / 2, max(width, 0) / 2)
        w = max(width, 0.0)
        path = (
            f"M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{height - 2 * r:.1f} "
            f"a{r},{r} 0 0 1 {-r},{r} h{-(w - r):.1f} z"
        )
        body = f"<title>{html.escape(tip)}</title>" if tip else ""
        self.parts.append(f'<path d="{path}" fill="{fill}">{body}</path>')

    def legend(self, x, y, items):
        """Legend keys mirror the marks: a dot for dots, a short tick for tick marks."""
        for item in items:
            color, label, shape = item if len(item) == 3 else (*item, "dot")
            if shape == "tick":
                self.line(x + 5, y - 11, x + 5, y + 3, color, 2, "round")
            else:
                self.dot(x + 5, y - 4, 5, color)
            self.text(x + 16, y, label, 12, INK_2)
            x += 30 + label_width(label, 12)

    def render(self) -> str:
        return "\n".join(self.parts + ["</svg>"]) + "\n"


def seconds(ms: float) -> str:
    return f"{ms / 1000:.2f} s"


def model_name(runs: dict, profile: str) -> str:
    return runs[profile]["server"]["model"].split("/")[-1]


def label_width(text: str, size: float) -> float:
    """Rough rendered width: CJK characters are about twice as wide as Latin ones."""
    return sum(size if ord(ch) > 0x2E80 else size * 0.54 for ch in text)


MODE_COLORS = {"vision": ACCENT, "text": GRAY, "compact": SKY}


def mode_label(mode: str, zh: bool) -> str:
    return pages.MODE_NAMES[mode][zh]


def latency_figure(runs: dict, summary: dict, zh: bool = False) -> str:
    tr = (lambda en, cn: cn) if zh else (lambda en, cn: en)
    width, row = 1040, 96
    top = 116
    height = top + len(PROFILES) * row + 64
    svg = Svg(
        width,
        height,
        tr("Time per decision", "每次决策耗时"),
        tr(
            "Round trip of every OpenJev call, one dot each, on a log scale. One call plans two "
            "pieces.",
            "每一次 OpenJev 调用的往返耗时，每个点一次调用，对数刻度；一次调用规划两个方块。",
        ),
        tr(
            "Strip plot of per-call latency for each profile and prompt, with medians.",
            "各档位、各提示方式逐次调用耗时的散点图及中位数。",
        ),
    )
    x0, x1 = 190, 740
    columns = (786, 880, 974)
    low, high = 20.0, 8000.0  # log axis: 20 ms to 8 s

    def px(ms: float) -> float:
        ms = min(max(ms, low), high)
        return x0 + (x1 - x0) * math.log(ms / low) / math.log(high / low)

    bottom = top + len(PROFILES) * row - 16
    for t in (50, 100, 250, 500, 1000, 2500, 5000):
        svg.line(px(t), top - 10, px(t), bottom, GRID)
        label = f"{t} ms" if t < 100 else f"{t / 1000:g} s"
        svg.text(px(t), bottom + 18, label, 11, MUTED, "middle")
    for x, mode in zip(columns, MODES, strict=True):
        svg.text(x, top - 18, mode_label(mode, zh).upper(), 10, MUTED, "middle", MONO)
    for i, profile in enumerate(PROFILES):
        cy = top + i * row + 28
        svg.text(32, cy - 2, profile, 15, INK_1, weight=600)
        svg.text(32, cy + 16, model_name(runs, profile), 11, MUTED, family=MONO)
        stats = summary["profiles"][profile]["modes"]
        for m, mode in enumerate(MODES):
            if mode not in stats:
                continue
            y = cy - 22 + 22 * m
            color = MODE_COLORS[mode]
            calls = [
                d["client_ms"]
                for g in runs[profile]["games"]
                if g["mode"] == mode
                for d in g["decisions"]
                if not d["forced"]
            ]
            for k, ms in enumerate(calls):
                jitter = ((k * 37) % 13 - 6) * 0.9
                svg.dot(px(ms), y + jitter, 2.6, color, 0.3, f"{profile} · {mode}: {ms:.0f} ms")
            median = stats[mode]["latency_ms"]["median"]
            svg.line(px(median), y - 9, px(median), y + 9, color, 2.5, "round")
            weight = 500 if mode == "compact" and profile == "max" else 400
            svg.text(
                columns[m],
                cy + 5,
                seconds(median),
                14,
                INK_1 if weight == 500 else INK_2,
                "middle",
                DISPLAY if weight == 500 else SANS,
                weight,
            )
    svg.legend(
        190,
        height - 22,
        [(MODE_COLORS[mode], mode_label(mode, zh)) for mode in MODES],
    )
    svg.text(width - 32, height - 22, "Apple M3 Max · llama.cpp on Metal", 11, MUTED, "end", MONO)
    return svg.render()


def thousands(value: int) -> str:
    return f"{value // 1000}k" if value else "0"


def outcomes_figure(runs: dict, summary: dict, zh: bool = False) -> str:
    tr = (lambda en, cn: cn) if zh else (lambda en, cn: en)
    width, row = 1040, 84
    top = 124
    height = top + len(PROFILES) * row + 60
    svg = Svg(
        width,
        height,
        tr("What 100 pieces look like", "100 个方块之后"),
        tr(
            "Five seeds per profile and prompt; every model sees the same pieces. "
            "One dot per game.",
            "每个档位、每种提示方式 5 个种子，所有模型面对相同的方块序列；每个点代表一局。",
        ),
        tr(
            "Dot plots of score, lines cleared and most holes per game, by profile and prompt, "
            "with the reference evaluator and random picks for comparison.",
            "按档位与提示方式展示每局的得分、消除行数与最多空洞，并标出参考评估器与随机选择的平均值。",
        ),
    )
    base = summary["baselines"]
    panels = (
        (
            "score",
            tr("Score", "得分"),
            16000,
            [0, 4000, 8000, 12000, 16000],
            thousands,
            "mean_score",
        ),
        ("lines", tr("Lines cleared", "消除行数"), 40, [0, 10, 20, 30, 40], str, "mean_lines"),
        (
            "max_holes",
            tr("Most holes at once", "最多空洞"),
            40,
            [0, 10, 20, 30, 40],
            str,
            "median_max_holes",
        ),
    )
    left, gap = 150, 36
    panel_w = (width - left - 32 - gap * 2) / 3
    bottom = top + len(PROFILES) * row - 16
    for p, (key, title, scale, ticks, fmt, base_key) in enumerate(panels):
        x0 = left + p * (panel_w + gap)
        svg.text(x0, top - 22, title, 13, INK_1, weight=600)
        for t in ticks:
            x = x0 + panel_w * t / scale
            svg.line(x, top - 10, x, bottom, GRID)
            svg.text(x, bottom + 18, fmt(t), 11, MUTED, "middle")
        for name, dash in (("reference", "none"), ("random", "3 3")):
            x = x0 + panel_w * min(base[name][base_key], scale) / scale
            svg.parts.append(
                f'<line x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{bottom}" stroke="{INK_2}" '
                f'stroke-width="1" stroke-dasharray="{dash}" opacity="0.55"/>'
            )
        for i, profile in enumerate(PROFILES):
            cy = top + i * row + 18
            stats = summary["profiles"][profile]["modes"]
            for m, mode in enumerate(MODES):
                if mode not in stats:
                    continue
                y = cy - 14 + 14 * m
                for seed, value in zip(stats[mode]["seeds"], stats[mode][key], strict=True):
                    svg.dot(
                        x0 + panel_w * min(value, scale) / scale,
                        y,
                        4.2,
                        MODE_COLORS[mode],
                        0.9,
                        f"{profile} · {mode} · seed {seed}: {value:,}",
                        stroke=SURFACE,
                    )
    for i, profile in enumerate(PROFILES):
        cy = top + i * row + 18
        svg.text(32, cy + 2, profile, 15, INK_1, weight=600)
        svg.text(32, cy + 20, model_name(runs, profile), 11, MUTED, family=MONO)
    legend = [(MODE_COLORS[mode], mode_label(mode, zh)) for mode in MODES]
    svg.legend(left, height - 22, legend)
    note = tr(
        "solid: reference evaluator · dashed: random picks", "实线：参考评估器 · 虚线：随机选择"
    )
    svg.text(width - 32, height - 22, note, 11, MUTED, "end", MONO)
    return svg.render()


def design_figure(summary: dict, zh: bool = False) -> str:
    tr = (lambda en, cn: cn) if zh else (lambda en, cn: en)
    row, top = 34, 118
    width, height = 1120, top + len(VARIANTS) * row + 44
    svg = Svg(
        width,
        height,
        tr("What Jev needs to see", "Jev 需要看到什么"),
        tr(
            f"48 fixed decision states, {len(VARIANTS)} presentations. Regret: value lost against "
            "the reference evaluator (lower is better).",
            f"48 个固定决策状态、{len(VARIANTS)} 种呈现方式。"
            "遗憾值：相对参考评估器损失的价值（越低越好）。",
        ),
        tr(
            "Horizontal bars of mean regret per presentation for each profile.",
            "各档位在每种呈现方式下的平均遗憾值条形图。",
        ),
    )
    left, gap = 262, 24
    count = len(PROFILES)
    panel_w = (width - left - 32 - gap * (count - 1)) / count
    scale = 2.8
    for i, (key, en, cn) in enumerate(VARIANTS):
        strong = key in ("vision", "compact")
        svg.text(
            32,
            top + i * row + 14,
            tr(en, cn),
            12.5,
            INK_1 if strong else INK_2,
            weight=600 if strong else 400,
        )
    ms_column, label_room = 58, 34
    bars = panel_w - ms_column - label_room  # length of the longest possible bar
    for p, profile in enumerate(PROFILES):
        x0 = left + p * (panel_w + gap)
        svg.text(x0, top - 22, profile, 13, INK_1, weight=600)
        svg.text(x0 + panel_w, top - 22, tr("MEDIAN", "中位数"), 9.5, MUTED, "end", MONO)
        results = summary["profiles"][profile]["ablation"]
        for t in (0, 1, 2):
            x = x0 + bars * t / scale
            svg.line(x, top - 8, x, top + len(VARIANTS) * row - 8, GRID)
            svg.text(x, top + len(VARIANTS) * row + 6, str(t), 11, MUTED, "middle")
        for i, (key, en, cn) in enumerate(VARIANTS):
            r = results.get(key)
            if r is None:
                continue
            y = top + i * row
            length = bars * min(r["mean_regret"], scale) / scale
            color = MODE_COLORS.get(key, GRAY)
            tip = f"{profile} · {tr(en, cn)}: {r['mean_regret']:.2f}, {r['median_ms']:.0f} ms"
            svg.bar(x0, y + 4, length, 14, color, tip)
            svg.text(x0 + length + 6, y + 15, f"{r['mean_regret']:.2f}", 11, INK_2)
            svg.text(x0 + panel_w, y + 15, f"{r['median_ms']:.0f} ms", 10.5, MUTED, "end", MONO)
    legend = tr(
        "Bars: mean regret per decision · MEDIAN: round trip per call",
        "条形：每次决策的平均遗憾值 · 中位数：单次调用往返耗时",
    )
    svg.text(32, height - 22, legend, 11, MUTED)
    note = tr("same states for every variant", "所有方式使用相同状态")
    svg.text(width - 32, height - 22, note, 11, MUTED, "end", MONO)
    return svg.render()


def replays(runs: dict) -> dict:
    """What the browser replay needs: seeds, choices, probabilities and timing per decision.

    Options are not stored; web/tetris.js rebuilds them and checks they match.
    """
    from video import quantization

    profiles = {}
    for profile in PROFILES:
        games = []
        for game in runs[profile]["games"]:
            decisions = []
            for d in game["decisions"]:
                image = d["image"]
                decisions.append(
                    {
                        "c": d["chosen"],
                        "p": [round(o["probability"], 4) for o in d["options"]],
                        "ms": d["client_ms"],
                        "s": d["server_ms"],
                        "t": d["input_tokens"],
                        "i": [image["width"], image["height"], image["tokens"]]
                        if image.get("tokens")
                        else None,
                        "k": d["confidence"],
                    }
                )
            keep = ("pieces", "lines", "clears", "score", "topped_out", "goal_reached")
            games.append(
                {
                    "seed": game["seed"],
                    "mode": game["mode"],
                    "result": {k: game["result"][k] for k in keep},
                    "decisions": decisions,
                }
            )
        profiles[profile] = {
            "model": runs[profile]["server"]["model"],
            "quant": quantization(profile),
            "games": games,
        }
    return {"schema": 1, "profiles": profiles}


def main() -> None:
    runs, ablation = load("runs"), load("ablation")
    baselines = json.loads((REPORT / "baselines.json").read_text())
    probes = {
        path.stem: json.loads(path.read_text())
        for path in sorted((REPORT / "probes").glob("*.json"))
    }
    compact = json.dumps(replays(runs), separators=(",", ":"))
    (REPORT / "replays.json").write_text(compact + "\n")
    summary = build_summary(runs, ablation, baselines)
    summary["probes"] = {
        name: {
            "median_ms": probe["median_ms"],
            "calls": len(probe["calls"]),
            "llama_cpp": probe["machine"]["llama_cpp"],
            "model": probe["server"]["model"],
        }
        for name, probe in probes.items()
    }
    (REPORT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    figures = REPORT / "figures"
    figures.mkdir(exist_ok=True)
    for zh, suffix in ((False, ""), (True, ".zh")):
        (figures / f"latency{suffix}.svg").write_text(latency_figure(runs, summary, zh))
        (figures / f"outcomes{suffix}.svg").write_text(outcomes_figure(runs, summary, zh))
        (figures / f"design{suffix}.svg").write_text(design_figure(summary, zh))
    pages.write(summary, runs, REPORT)
    print("wrote summary.json, replays.json, figures/, README.md, README.zh-CN.md, index.html")


if __name__ == "__main__":
    main()
