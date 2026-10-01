"""Build the Tetris test report from the recorded runs.

    uv run python examples/tetris/report.py

Reads report/runs/*.json and report/ablation/*.json and writes report/summary.json,
the SVG figures, report/README.md (+ zh-CN) and the visual report/index.html. No
inference happens here: every number comes from the recordings.
"""

from __future__ import annotations

import html
import json
import statistics
from pathlib import Path

import pages

HERE = Path(__file__).resolve().parent
REPORT = HERE / "report"
PROFILES = ("fast", "balanced", "quality")
MODES = ("vision", "text")
VARIANTS = tuple((key, en, zh) for key, (en, zh) in pages.VARIANT_NAMES.items())

# Chart tokens: the documentation site's dark surface, brand accent and a de-emphasis
# gray (emphasis pair: CVD ΔE 27.5, contrast 13.5:1 and 5.3:1 on the surface).
SURFACE, BORDER, GRID, AXIS = "#141e16", "#2b382e", "#223025", "#3a4b38"
INK_1, INK_2, MUTED = "#eef1e9", "#acb7ac", "#7f967a"
ACCENT, GRAY = "#b4f784", "#7f967a"
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


def build_summary(runs: dict, ablation: dict) -> dict:
    first = runs["balanced"]
    return {
        "schema": 1,
        "measured": {p: runs[p]["measured"] for p in PROFILES},
        "machine": first["machine"],
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


def latency_figure(runs: dict, summary: dict, zh: bool = False) -> str:
    tr = (lambda en, cn: cn) if zh else (lambda en, cn: en)
    width, height = 960, 372
    svg = Svg(
        width,
        height,
        tr("Time per decision", "每次决策耗时"),
        tr(
            "Round trip of every OpenJev call in vision mode (one dot each). "
            "One call plans two pieces.",
            "视觉模式下每一次 OpenJev 调用的往返耗时（每个点一次调用），一次调用规划两个方块。",
        ),
        tr(
            "Strip plot of per-call latency for the fast, balanced and quality profiles.",
            "fast、balanced、quality 三个档位逐次调用耗时的散点图。",
        ),
    )
    x0, x1, top, row = 190, 680, 108, 72
    columns = (716, 808, 872)
    scale = 1800.0

    def px(ms: float) -> float:
        return x0 + (x1 - x0) * min(ms, scale) / scale

    for t in range(0, 1801, 300):
        svg.line(px(t), top - 10, px(t), top + 3 * row - 14, GRID)
        label = "0" if t == 0 else f"{t / 1000:.1f} s"
        svg.text(px(t), top + 3 * row + 4, label, 11, MUTED, "middle")
    for x, head in zip(
        columns, (tr("MEDIAN", "中位数"), "P90", tr("TEXT-ONLY", "纯文字")), strict=True
    ):
        svg.text(x, top - 18, head, 10, MUTED, family=MONO)
    for i, profile in enumerate(PROFILES):
        cy = top + i * row + 20
        svg.text(32, cy - 2, profile, 15, INK_1, weight=600)
        svg.text(32, cy + 16, model_name(runs, profile), 11, MUTED, family=MONO)
        calls = [
            d["client_ms"]
            for g in runs[profile]["games"]
            if g["mode"] == "vision"
            for d in g["decisions"]
            if not d["forced"]
        ]
        for k, ms in enumerate(calls):
            jitter = ((k * 37) % 23 - 11) * 1.2
            svg.dot(px(ms), cy + jitter, 3.2, ACCENT, 0.32, f"{profile}: {ms:.0f} ms")
        stats = summary["profiles"][profile]["modes"]
        median = stats["vision"]["latency_ms"]["median"]
        svg.line(px(median), cy - 22, px(median), cy + 22, INK_1, 2, "round")
        text_median = stats["text"]["latency_ms"]["median"]
        svg.line(px(text_median), cy - 14, px(text_median), cy + 14, GRAY, 2, "round")
        svg.text(columns[0], cy + 5, seconds(median), 15, INK_1, family=DISPLAY, weight=500)
        svg.text(columns[1], cy + 5, seconds(stats["vision"]["latency_ms"]["p90"]), 13, INK_2)
        svg.text(columns[2], cy + 5, seconds(text_median), 13, INK_2)
    svg.legend(
        190,
        height - 22,
        [
            (ACCENT, tr("vision call", "视觉模式调用")),
            (INK_1, tr("vision median", "视觉模式中位数"), "tick"),
            (GRAY, tr("text-only median", "纯文字提示中位数"), "tick"),
        ],
    )
    svg.text(width - 32, height - 22, "Apple M3 Max · llama.cpp b9670", 11, MUTED, "end", MONO)
    return svg.render()


def thousands(value: int) -> str:
    return f"{value // 1000}k" if value else "0"


def outcomes_figure(runs: dict, summary: dict, zh: bool = False) -> str:
    tr = (lambda en, cn: cn) if zh else (lambda en, cn: en)
    width, height = 960, 400
    svg = Svg(
        width,
        height,
        tr("What 100 pieces look like", "100 个方块之后"),
        tr(
            "Five seeds per profile; every model sees the same piece sequences. One dot per game.",
            "每个档位 5 个种子，所有模型面对相同的方块序列；每个点代表一局。",
        ),
        tr(
            "Dot plots of score, lines cleared and most holes per game, "
            "by profile and prompt mode.",
            "按档位与提示方式展示每局的得分、消除行数与最多空洞。",
        ),
    )
    panels = (
        ("score", tr("Score", "得分"), 16000, [0, 4000, 8000, 12000, 16000], thousands),
        ("lines", tr("Lines cleared", "消除行数"), 40, [0, 10, 20, 30, 40], str),
        ("max_holes", tr("Most holes at once", "最多空洞"), 40, [0, 10, 20, 30, 40], str),
    )
    left, gap, top, row = 150, 36, 120, 70
    panel_w = (width - left - 32 - gap * 2) / 3
    for p, (key, title, scale, ticks, fmt) in enumerate(panels):
        x0 = left + p * (panel_w + gap)
        svg.text(x0, top - 22, title, 13, INK_1, weight=600)
        for t in ticks:
            x = x0 + panel_w * t / scale
            svg.line(x, top - 10, x, top + 3 * row - 16, GRID)
            svg.text(x, top + 3 * row + 2, fmt(t), 11, MUTED, "middle")
        for i, profile in enumerate(PROFILES):
            cy = top + i * row + 18
            stats = summary["profiles"][profile]["modes"]
            for m, (mode, color) in enumerate((("vision", ACCENT), ("text", GRAY))):
                y = cy - 8 + 16 * m
                values = stats[mode][key]
                for seed, value in zip(stats[mode]["seeds"], values, strict=True):
                    svg.dot(
                        x0 + panel_w * min(value, scale) / scale,
                        y,
                        4.5,
                        color,
                        0.85,
                        f"{profile} · {mode} · seed {seed}: {value:,}",
                        stroke=SURFACE,
                    )
    for i, profile in enumerate(PROFILES):
        cy = top + i * row + 18
        svg.text(32, cy + 2, profile, 15, INK_1, weight=600)
        svg.text(32, cy + 20, model_name(runs, profile), 11, MUTED, family=MONO)
    legend = [
        (ACCENT, tr("vision: facts + outcome sheet", "视觉：文字事实 + 结果缩略图")),
        (GRAY, tr("text-only prompt", "纯文字提示")),
    ]
    svg.legend(left, height - 22, legend)
    seeds = tr("seeds", "种子") + " 101 · 202 · 303 · 404 · 505"
    svg.text(width - 32, height - 22, seeds, 11, MUTED, "end", MONO)
    return svg.render()


def design_figure(summary: dict, zh: bool = False) -> str:
    tr = (lambda en, cn: cn) if zh else (lambda en, cn: en)
    width, height = 960, 452
    svg = Svg(
        width,
        height,
        tr("What Jev needs to see", "Jev 需要看到什么"),
        tr(
            "48 fixed decision states, eight presentations. Regret: value lost against the "
            "reference evaluator (lower is better).",
            "48 个固定决策状态、8 种呈现方式。遗憾值：相对参考评估器损失的价值（越低越好）。",
        ),
        tr(
            "Horizontal bars of mean regret per presentation for each profile.",
            "各档位在每种呈现方式下的平均遗憾值条形图。",
        ),
    )
    left, gap, top, row = 262, 28, 118, 34
    panel_w = (width - left - 32 - gap * 2) / 3
    scale = 2.8
    for i, (_, en, cn) in enumerate(VARIANTS):
        first = i == 0
        svg.text(
            32,
            top + i * row + 14,
            tr(en, cn),
            12.5,
            INK_1 if first else INK_2,
            weight=600 if first else 400,
        )
    ms_column, label_room = 62, 36
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
            r = results[key]
            y = top + i * row
            length = bars * min(r["mean_regret"], scale) / scale
            color = ACCENT if key == "vision" else GRAY
            tip = f"{profile} · {tr(en, cn)}: {r['mean_regret']:.2f}, {r['median_ms']:.0f} ms"
            svg.bar(x0, y + 4, length, 14, color, tip)
            svg.text(x0 + length + 6, y + 15, f"{r['mean_regret']:.2f}", 11, INK_2)
            svg.text(x0 + panel_w, y + 15, f"{r['median_ms']:.0f} ms", 10.5, MUTED, "end", MONO)
    legend = tr(
        "Bars: mean regret per decision · MEDIAN: round trip per call",
        "条形：每次决策的平均遗憾值 · 中位数：单次调用往返耗时",
    )
    svg.text(32, height - 22, legend, 11, MUTED)
    note = tr("same states and prompt for every variant", "所有方式使用相同状态与提示词")
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
    compact = json.dumps(replays(runs), separators=(",", ":"))
    (REPORT / "replays.json").write_text(compact + "\n")
    summary = build_summary(runs, ablation)
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
