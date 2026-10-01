"""Render recorded latency receipts as markdown tables and, with --chart, theme-aware SVG
charts in English and Chinese. No inference.

uv run python scripts/render_performance.py [receipts ...] [--chart [PROFILE]]
    [--series before,after,mlx]
"""

import argparse
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERIES = {  # receipt endpoint: (English name, Chinese name, css class)
    "before": ("Before", "优化前", "s0"),
    "after": ("After", "优化后", "s1"),
    "mlx": ("MLX engine (not shipped)", "MLX 引擎（未发布）", "s2"),
}
SHIPPED = "before,after"
PANELS = [
    (
        ("One question", "一个问题"),
        ["text_1q", "long_1q", "screenshot_1q", "photo_1q", "repeat_1q"],
    ),
    (
        ("Four questions about the same state", "同一 state 的四个问题"),
        ["text_4q", "long_4q", "screenshot_4q"],
    ),
]
LABELS = {
    "text": ("Support ticket", "客服工单"),
    "long": ("1.2k-token policy", "1.2k token 条款"),
    "screenshot": ("448×672 screenshot", "448×672 截图"),
    "photo": ("2048×1536 photo", "2048×1536 照片"),
    "repeat": ("Repeated request", "重复请求"),
}
FONT = "system-ui,-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif"
STYLE = f"""
.viz{{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;
--axis:#c3c2b7;--s0:#b4b3ac;--s1:#2a78d6;--s2:#eb6834}}
@media (prefers-color-scheme:dark){{.viz{{--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--s0:#5c5b56;--s1:#3987e5;--s2:#d95926}}}}
text{{font-family:{FONT}}}.bg{{fill:var(--surface)}}
.title{{fill:var(--ink);font-size:15px;font-weight:600}}.sub{{fill:var(--ink2);font-size:12px}}
.head{{fill:var(--ink);font-size:13px;font-weight:600}}.cat{{fill:var(--ink2);font-size:12px}}
.val{{fill:var(--ink2);font-size:11px;font-variant-numeric:tabular-nums}}
.tick{{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}}
.grid{{stroke:var(--grid)}}.axis{{stroke:var(--axis)}}
.s0{{fill:var(--s0)}}.s1{{fill:var(--s1)}}.s2{{fill:var(--s2)}}
"""
WIDTH, LEFT, RIGHT = 760, 190, 70
THICK, GAP, GROUP = 10, 2, 14  # bar thickness, surface gap between bars, gap between cases


def fmt(ms: float) -> str:
    return f"{ms / 1000:.2f} s" if ms >= 1000 else f"{ms:.0f} ms"


def label(case: str, zh: bool) -> str:
    return LABELS[case.rsplit("_", 1)[0]][zh]


def width(value: str, size: float = 12) -> float:
    """Approximate rendered width: CJK characters are square, Latin ones about 0.55 em."""
    return sum(size if ord(ch) > 0x2E80 else size * 0.55 for ch in value)


def nice(limit: float) -> list[float]:
    """Clean tick values from zero past `limit`, at most seven."""
    for step in (50, 100, 200, 250, 500, 1000, 2000, 2500, 5000):
        if limit / step <= 6:
            top = step * -(-limit // step)
            return [i * step for i in range(int(top // step) + 1)]
    return [0, limit]


def bar(x0: float, y: float, width: float, height: float, radius: float = 4) -> str:
    """Path of a bar with a rounded data end on the right, square at the baseline."""
    r = min(radius, height / 2, width)
    x1 = x0 + width
    return (
        f"M{x0:.1f},{y:.1f}H{x1 - r:.1f}Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f}"
        f"V{y + height - r:.1f}Q{x1:.1f},{y + height:.1f} {x1 - r:.1f},{y + height:.1f}H{x0:.1f}Z"
    )


def text(css: str, x: float, y: float, value: str, anchor: str = "start") -> str:
    return (
        f'<text class="{css}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def line(css: str, x1: float, y1: float, x2: float, y2: float) -> str:
    return f'<line class="{css}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>'


def render(receipt: dict, series: list[str], title: str, subtitle: str, zh: bool = False) -> str:
    block = len(series) * (THICK + GAP) - GAP  # one case: its bars stacked vertically
    plot = WIDTH - LEFT - RIGHT
    height = 80 + sum(30 + len(cases) * (block + GROUP) + 50 for _, cases in PANELS)
    parts = [
        f'<rect class="bg" width="{WIDTH}" height="{height}" rx="12"/>',
        text("title", 24, 34, title),
        text("sub", 24, 54, subtitle),
    ]
    x = 24.0
    for key in series:  # the legend: always present for two or more series
        name, css = SERIES[key][zh], SERIES[key][2]
        parts.append(f'<rect class="{css}" x="{x:.1f}" y="68" width="12" height="12" rx="3"/>')
        parts.append(text("cat", x + 18, 78, name))
        x += 18 + width(name) + 22
    y = 104.0
    for heading, cases in PANELS:
        summaries = [receipt["cases"][case]["summary"] for case in cases]
        ticks = nice(max(s[key]["median_ms"] for s in summaries for key in series) * 1.12)
        scale = plot / ticks[-1]
        parts.append(text("head", 24, y + 14, heading[zh]))
        y += 30
        bottom = y + len(cases) * (block + GROUP) - GROUP
        for tick in ticks:
            tx = LEFT + tick * scale
            parts.append(line("grid", tx, y - 6, tx, bottom))
            parts.append(text("tick", tx, bottom + 18, fmt(tick), "middle"))
        parts.append(line("axis", LEFT, y - 6, LEFT, bottom))
        for case, summary in zip(cases, summaries, strict=True):
            parts.append(text("cat", LEFT - 12, y + block / 2 + 4, label(case, zh), "end"))
            for key in series:
                ms = summary[key]["median_ms"]
                length = max(ms * scale, 2)
                tip = escape(f"{label(case, zh)} · {SERIES[key][zh]}: {fmt(ms)}")
                shape = bar(LEFT, y, length, THICK)
                parts.append(
                    f'<path class="{SERIES[key][2]}" d="{shape}"><title>{tip}</title></path>'
                )
                parts.append(text("val", LEFT + length + 6, y + THICK - 1, fmt(ms)))
                y += THICK + GAP
            y += GROUP - GAP
        y = bottom + 50
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="viz" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="title desc">'
        f'<style>{STYLE}</style><title id="title">{escape(title)}</title>'
        f'<desc id="desc">{escape(subtitle)}</desc>' + "".join(parts) + "</svg>\n"
    )


def name(case: str, zh: bool) -> str:
    if case.startswith("repeat"):
        return label(case, zh)
    count = int(case[-2])
    if zh:
        return f"{label(case, zh)} · {count} 个问题"
    return f"{label(case, zh)} · {count} question{'s' * (count > 1)}"


def change(ms: float, base: float) -> str:
    return f"{(ms - base) / base * 100:+.0f}%".replace("-", "−")


def model(receipt: dict) -> str:
    return next(iter(receipt["endpoints"].values()))["model"].split("/")[-1]


def table(receipt: dict, series: list[str], zh: bool = False) -> str:
    """One profile: the median of each variant, compared with the original code."""
    header = ["请求" if zh else "Request"]
    for key in series:
        header.append(SERIES[key][zh])
        if key != "before":
            header.append("变化" if zh else "Change")
    rows = ["| " + " | ".join(header) + " |", "| --- |" + " ---: |" * (len(header) - 1)]
    for _, cases in PANELS:
        for case in cases:
            summary = receipt["cases"][case]["summary"]
            cells = [name(case, zh)]
            for key in series:
                ms = summary[key]["median_ms"]
                cells.append(fmt(ms))
                if key != "before":
                    cells.append(change(ms, summary["before"]["median_ms"]))
            rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def compare(receipts: dict[str, dict], zh: bool = False) -> str:
    """Profiles side by side, one table per panel: the optimized median and its change."""
    header = [""] + [
        f'{profile} <span class="model">{model(receipt).split("-", 1)[1]}</span>'
        for profile, receipt in receipts.items()
    ]
    tables = []
    for heading, cases in PANELS:
        rows = [f"**{heading[zh]}**", "", "| " + " | ".join(header) + " |"]
        rows.append("| --- |" + " ---: |" * len(receipts))
        for case in cases:
            cells = [label(case, zh)]
            for receipt in receipts.values():
                summary = receipt["cases"][case]["summary"]
                ms, base = summary["after"]["median_ms"], summary["before"]["median_ms"]
                cells.append(f'{fmt(ms)} <span class="delta">{change(ms, base)}</span>')
            rows.append("| " + " | ".join(cells) + " |")
        tables.append("\n".join(rows))
    return "\n\n".join(tables)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "receipts",
        nargs="*",
        type=Path,
        default=[
            ROOT / f"benchmarks/performance/{p}.json" for p in ("fast", "balanced", "quality")
        ],
    )
    parser.add_argument(
        "--chart", nargs="?", const="balanced", metavar="PROFILE", help="write the SVG charts"
    )
    parser.add_argument(
        "--series",
        help="also print one table per profile with these endpoints, e.g. before,after,mlx",
    )
    args = parser.parse_args()
    receipts = {path.stem: json.loads(path.read_text()) for path in args.receipts}
    if args.chart:
        receipt = receipts[args.chart]
        series = [key for key in (args.series or SHIPPED).split(",") if key in receipt["endpoints"]]
        trials = receipt["trials"]
        for zh, file in ((False, "performance.svg"), (True, "performance.zh.svg")):
            if zh:
                title = f"请求延迟中位数 · {model(receipt)} · {receipt['chip']}"
                subtitle = f"每种请求交替测量 {trials} 次 · 除重复请求外每次都是新 state · 越短越好"
            else:
                title = f"Median request latency · {model(receipt)} · {receipt['chip']}"
                subtitle = (
                    f"{trials} interleaved trials per case · a new state on every request "
                    "except the repeat · lower is better"
                )
            target = ROOT / "site/public" / file
            target.write_text(render(receipt, series, title, subtitle, zh))
            print("wrote", target.relative_to(ROOT))
    print(compare(receipts), compare(receipts, zh=True), sep="\n\n")
    if args.series:
        for profile, receipt in receipts.items():
            series = [key for key in args.series.split(",") if key in receipt["endpoints"]]
            print(f"\n{profile}\n\n{table(receipt, series)}")


if __name__ == "__main__":
    main()
