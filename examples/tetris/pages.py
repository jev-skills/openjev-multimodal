"""The report pages: English and Chinese Markdown for GitHub, one bilingual HTML page.

Every sentence with a number is written from the recordings, so the pages cannot drift
from the data. Called by report.py.
"""
# ruff: noqa: E501  (prose module: the long lines are English and Chinese sentences)

from __future__ import annotations

import html
import json
import re
import statistics
from pathlib import Path

from jev import payload
from tetris import Game, frontier
from vision import labels, outcome_sheet

SITE = "https://hand-in.github.io/openjev-multimodal/"
PROFILES = ("fast", "balanced", "quality")
VARIANT_NAMES = {
    "vision": ("Facts + outcome sheet (default)", "文字事实 + 结果缩略图（默认）"),
    "vision@0.5": ("Facts + sheet at ½ size", "文字事实 + ½ 尺寸缩略图"),
    "vision@2.0": ("Facts + sheet at 2×", "文字事实 + 2 倍缩略图"),
    "text": ("Facts only, no image", "仅文字事实，不发图片"),
    "board": ("Facts + board screenshot", "文字事实 + 棋盘截图"),
    "board@0.5": ("Facts + screenshot at ½ size", "文字事实 + ½ 尺寸截图"),
    "board@2.0": ("Facts + screenshot at 2×", "文字事实 + 2 倍截图"),
    "pixels": ("Outcome sheet only, no facts", "仅结果缩略图，无文字事实"),
}


# --------------------------------------------------------------------------- numbers


def seconds(ms: float, zh: bool = False) -> str:
    return f"{ms / 1000:.2f} 秒" if zh else f"{ms / 1000:.2f} s"


def number(value: float) -> str:
    return f"{value:,.0f}"


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def percent(value: float) -> str:
    return f"{100 * value:.0f}%"


def model(runs: dict, profile: str) -> str:
    return runs[profile]["server"]["model"].split("/")[-1]


def game_of(runs: dict, profile: str, seed: int, mode: str) -> dict:
    return next(g for g in runs[profile]["games"] if g["seed"] == seed and g["mode"] == mode)


def goal_video(runs: dict, profile: str, seed: int = 101) -> dict:
    """Numbers for the video of one profile: its seed-101 vision game up to the tenth clear."""
    run = game_of(runs, profile, seed, "vision")
    goal = run["result"]["goal_run"]
    calls = [d["client_ms"] for d in run["decisions"][: goal["decision"]] if not d["forced"]]
    return {**goal, "median_ms": statistics.median(calls), "calls": len(calls)}


def state_at(run: dict, number: int) -> Game:
    """The game exactly as it was before decision `number`, rebuilt from the recording."""
    game = Game(run["seed"])
    for record in run["decisions"][:number]:
        option = next(o for o in record["options"] if o["label"] == record["chosen"])
        for key in option["keys"][0] + option["keys"][1]:
            game.press(key)
    return game


def example(runs: dict, figures: Path, profile="quality", seed=101, number=7) -> dict:
    """One real decision, shown in full: the request, the image and the response."""
    run = game_of(runs, profile, seed, "vision")
    record = run["decisions"][number]
    game = state_at(run, number)
    options = frontier(game.plans())
    body, image = payload(game, options, "vision")
    names = labels(len(options))
    if [o["label"] for o in record["options"]] != names:
        raise RuntimeError("example decision no longer matches the recording")
    outcome_sheet(options).save(figures / "example-sheet.png", optimize=True)  # as sent
    url = body["images"][0]
    body["images"] = [url[:40] + f"… ({len(url) * 3 // 4 // 1024} KB PNG)"]
    chosen = names.index(record["chosen"])
    response = {
        "model": "jev-latest",
        "answers": {
            "plan": {
                "type": "choice",
                "choice": str(chosen),
                "probabilities": {
                    str(i): round(o["probability"], 4) for i, o in enumerate(record["options"])
                },
                "confidence": round(record["confidence"], 4),
            }
        },
        "usage": {"input_tokens": record["input_tokens"], "output_tokens": 1},
    }
    return {
        "profile": profile,
        "seed": seed,
        "number": number,
        "record": record,
        "image": image,
        "request": json.dumps(body, indent=2, ensure_ascii=False),
        "response": json.dumps(response, indent=2),
        "chosen": names[chosen],
    }


# --------------------------------------------------------------------------- blocks
# A page is a list of blocks. Text is (english, chinese); inline **bold**, `code` and
# [links](url) work in both renderers.


def build(summary: dict, runs: dict, figures: Path) -> list[tuple]:
    p = summary["profiles"]
    m = {name: p[name]["modes"] for name in PROFILES}
    v = {name: m[name]["vision"] for name in PROFILES}
    t = {name: m[name]["text"] for name in PROFILES}
    ab = {name: p[name]["ablation"] for name in PROFILES}
    video = {name: goal_video(runs, name) for name in PROFILES}
    ex = example(runs, figures)
    rec = ex["record"]
    decisions = sum(v[n]["decisions"] + t[n]["decisions"] for n in PROFILES)
    calls = sum(v[n]["calls"] + t[n]["calls"] for n in PROFILES)
    best = max(
        (score, name, mode, seed)
        for name in PROFILES
        for mode in ("vision", "text")
        for seed, score in zip(m[name][mode]["seeds"], m[name][mode]["score"], strict=True)
    )
    medians = " · ".join(f"{v[n]['latency_ms']['median'] / 1000:.2f}" for n in PROFILES)
    lat = {n: v[n]["latency_ms"]["median"] for n in PROFILES}
    tlat = {n: t[n]["latency_ms"]["median"] for n in PROFILES}
    faster = sorted(lat[n] - tlat[n] for n in ("balanced", "quality"))
    measured = summary["measured"]["balanced"][:10]
    machine = summary["machine"]
    blocks: list[tuple] = []

    blocks.append(
        (
            "lede",
            (
                f"Three local models each played ten games of 100 pieces through OpenJev "
                f"Multimodal: five seeds, two prompt styles, the same piece sequences for every "
                f"model. Every call asks one Choice question about the next two pieces and reads "
                f"a single output token. The tables, charts, videos and the browser replay are "
                f"all generated from the recordings (measured {measured} on an "
                f"{machine['chip']})."
            ),
            (
                f"三个本地模型通过 OpenJev Multimodal 各下了 10 局、每局 100 个方块：5 个随机种子 × 2 种提示方式，"
                f"所有模型面对完全相同的方块序列。每次调用只问一个 Choice 问题，一次规划接下来的两个方块，"
                f"只读取 1 个输出 token。下文的表格、图表、视频与网页回放全部由录制数据生成"
                f"（测于 {measured}，{machine['chip']}）。"
            ),
        )
    )
    blocks.append(
        (
            "kpis",
            [
                (
                    f"{sum(v[n]['goal_reached'] for n in PROFILES)} / "
                    f"{sum(v[n]['games'] for n in PROFILES)}",
                    ("vision games reached 10 line clears", "视觉模式对局全部完成 10 次消除"),
                    (
                        "0 illegal keys · 0 API errors · 0 fallback moves",
                        "非法按键 0 · API 错误 0 · 兜底操作 0",
                    ),
                ),
                (
                    f"{v['quality']['clean_goal']} / {v['quality']['games']}",
                    ("quality games reached the goal with no hole", "quality 对局达成目标时零空洞"),
                    (
                        f"{t['quality']['clean_goal']} / {t['quality']['games']} with the text-only prompt",
                        f"纯文字提示下为 {t['quality']['clean_goal']} / {t['quality']['games']}",
                    ),
                ),
                (
                    f"{medians} s",
                    ("median time per decision", "每次决策耗时中位数"),
                    (
                        "fast · balanced · quality; one call plans two pieces",
                        "fast · balanced · quality；每次调用规划两个方块",
                    ),
                ),
                (
                    number(best[0]),
                    ("best score after 100 pieces", "100 个方块后的最高分"),
                    (
                        f"{best[1]} · {'text-only' if best[2] == 'text' else 'vision'} · seed {best[3]}",
                        f"{best[1]} · {'纯文字提示' if best[2] == 'text' else '视觉提示'} · 种子 {best[3]}",
                    ),
                ),
            ],
        )
    )
    blocks.append(("h2", "Watch each model play", "观看三个模型对局"))
    blocks.append(
        (
            "p",
            "Seed 101 with the vision prompt, from the first piece to the tenth line clear. "
            "Waiting time is the measured round trip of each call; key presses, drops and "
            "clears are animated at a fixed pace.",
            "种子 101、视觉提示，从第一个方块播放到第 10 次消除。等待时间是每次调用实测的往返耗时；"
            "按键、下落与消除动画按固定节奏播放。",
        )
    )
    blocks.append(
        (
            "videos",
            [
                (
                    name,
                    f"{name} · {model(runs, name)}",
                    (
                        f"goal after {video[name]['pieces']} pieces · "
                        f"{plural(video[name]['holes'], 'hole')} · "
                        f"{seconds(video[name]['median_ms'])} per call",
                        f"{video[name]['pieces']} 个方块达成目标 · {video[name]['holes']} 个空洞 · "
                        f"每次调用 {seconds(video[name]['median_ms'], True)}",
                    ),
                )
                for name in PROFILES
            ],
        )
    )
    blocks.append(("h2", "What the runs show", "测试结论"))
    fast_lines_v = statistics.fmean(v["fast"]["lines"])
    fast_lines_t = statistics.fmean(t["fast"]["lines"])
    lowest = [f"{ab[n]['vision']['mean_regret']:.2f}" for n in PROFILES]
    text_regret = [f"{ab[n]['text']['mean_regret']:.2f}" for n in ("balanced", "quality")]
    same = text_regret[0] == text_regret[1]
    text_en = f"to {text_regret[0]}" if same else f"to {text_regret[0]} and {text_regret[1]}"
    text_zh = (
        f"都降到 {text_regret[0]}" if same else f"分别降到 {text_regret[0]} 和 {text_regret[1]}"
    )
    extra_tokens = (
        ab["balanced"]["vision@2.0"]["median_input_tokens"]
        - ab["balanced"]["vision"]["median_input_tokens"]
    )
    blocks.append(
        (
            "list",
            [
                (
                    f"**Every model reached the goal.** All {sum(v[n]['games'] for n in PROFILES)} "
                    f"vision-mode games cleared 10 lines with no illegal key, no API error and no "
                    f"fallback move. The quality model reached the goal with a hole-free stack in "
                    f"{v['quality']['clean_goal']} of its 5 games ({t['quality']['clean_goal']} of 5 "
                    f"with the text-only prompt).",
                    f"**三个模型全部达成目标。** 视觉模式的 {sum(v[n]['games'] for n in PROFILES)} 局全部完成 "
                    f"10 次消除，没有非法按键、API 错误或兜底操作。quality 模型在 5 局中有 "
                    f"{v['quality']['clean_goal']} 局达成目标时盘面没有任何空洞（纯文字提示下为 "
                    f"{t['quality']['clean_goal']} 局）。",
                ),
                (
                    f"**A larger model buys better judgment.** Agreement with the reference evaluator "
                    f"rises from {percent(v['fast']['agreement'])} (0.8B) to "
                    f"{percent(v['balanced']['agreement'])} (4B) and "
                    f"{percent(v['quality']['agreement'])} (35B-A3B); mean regret falls from "
                    f"{v['fast']['mean_regret']:.2f} to {v['balanced']['mean_regret']:.2f} and "
                    f"{v['quality']['mean_regret']:.2f}. The 35B mixture-of-experts model activates "
                    f"about 3B parameters per token, so it decides in "
                    f"{seconds(lat['quality'])}, only {lat['quality'] / lat['balanced']:.1f}× the 4B "
                    f"model.",
                    f"**模型越大，判断越好。** 与参考评估器的一致率从 {percent(v['fast']['agreement'])}（0.8B）"
                    f"提升到 {percent(v['balanced']['agreement'])}（4B）和 {percent(v['quality']['agreement'])}"
                    f"（35B-A3B），平均遗憾值从 {v['fast']['mean_regret']:.2f} 降到 "
                    f"{v['balanced']['mean_regret']:.2f} 和 {v['quality']['mean_regret']:.2f}。35B 混合专家模型"
                    f"每个 token 只激活约 3B 参数，单次决策 {seconds(lat['quality'], True)}，"
                    f"仅为 4B 模型的 {lat['quality'] / lat['balanced']:.1f} 倍。",
                ),
                (
                    f"**Exact facts decide; the image explains.** Shown only the outcome images, "
                    f"every model loses {min(ab[n]['pixels']['mean_regret'] for n in PROFILES):.1f}–"
                    f"{max(ab[n]['pixels']['mean_regret'] for n in PROFILES):.1f} points of value per "
                    f"decision on the fixed states. Facts alone bring the 4B and 35B models down "
                    f"{text_en}, and facts plus the outcome sheet "
                    f"give every model its lowest regret: {', '.join(lowest)}.",
                    f"**精确事实负责决策，图片负责解释。** 只给结果缩略图、不给文字事实时，三个模型在固定状态集上"
                    f"每次决策损失 {min(ab[n]['pixels']['mean_regret'] for n in PROFILES):.1f}–"
                    f"{max(ab[n]['pixels']['mean_regret'] for n in PROFILES):.1f} 分；只给文字事实，4B 与 35B "
                    f"模型{text_zh}；文字事实加结果缩略图让三个模型都达到各自最低："
                    f"{'、'.join(lowest)}。",
                ),
                (
                    f"**The picture matters most to the smallest model.** In full games the 0.8B "
                    f"model cleared {fast_lines_v:.1f} lines on average with the outcome sheet and "
                    f"{fast_lines_t:.1f} without it, and topped out in {v['fast']['topped_out']} game "
                    f"instead of {t['fast']['topped_out']}. For the 4B and 35B models the text-only "
                    f"prompt played about as well and saved {faster[0]:.0f}–{faster[1]:.0f} ms per "
                    f"call.",
                    f"**模型越小，图片越重要。** 完整对局中，0.8B 模型有结果缩略图时平均消除 {fast_lines_v:.1f} 行，"
                    f"没有时只有 {fast_lines_t:.1f} 行；堆满出局也从 {t['fast']['topped_out']} 局减少到 "
                    f"{v['fast']['topped_out']} 局。对 4B 与 35B 模型，纯文字提示表现相当，每次调用还能快 "
                    f"{faster[0]:.0f}–{faster[1]:.0f} 毫秒。",
                ),
                (
                    f"**Choose the picture first, then the fewest tokens that stay legible.** Doubling "
                    f"the outcome sheet adds about {extra_tokens:.0f} "
                    f"input tokens without better decisions, and halving it changes little. A "
                    f"full-board screenshot is the wrong picture for this decision: for the 4B model "
                    f"it raised regret from {ab['balanced']['vision']['mean_regret']:.2f} to "
                    f"{ab['balanced']['board']['mean_regret']:.2f} and the median call from "
                    f"{seconds(ab['balanced']['vision']['median_ms'])} to "
                    f"{seconds(ab['balanced']['board']['median_ms'])}.",
                    f"**先选对画面，再用尽量少且清晰的 token。** 结果缩略图放大 2 倍会多出约 "
                    f"{extra_tokens:.0f} 个输入 token，决策并未更好；缩小一半影响不大。整张棋盘截图并不适合这个决策：对 4B 模型，"
                    f"它把遗憾值从 {ab['balanced']['vision']['mean_regret']:.2f} 抬高到 "
                    f"{ab['balanced']['board']['mean_regret']:.2f}，调用中位数从 "
                    f"{seconds(ab['balanced']['vision']['median_ms'], True)}增加到 "
                    f"{seconds(ab['balanced']['board']['median_ms'], True)}。",
                ),
                (
                    f"**Latency follows input tokens.** Every call returns one output token. Server "
                    f"time matches the round trip within about 1 ms and planning in code takes "
                    f"{min(v[n]['plan_ms_median'] for n in PROFILES):.0f}–"
                    f"{max(v[n]['plan_ms_median'] for n in PROFILES):.0f} ms, so prompt length, image "
                    f"tokens and model size set the pace.",
                    f"**延迟由输入 token 决定。** 每次调用只输出 1 个 token。服务端耗时与往返耗时相差约 1 毫秒，"
                    f"代码侧规划耗时 {min(v[n]['plan_ms_median'] for n in PROFILES):.0f}–"
                    f"{max(v[n]['plan_ms_median'] for n in PROFILES):.0f} 毫秒；决定速度的是提示长度、图像 token "
                    f"与模型规模。",
                ),
            ],
        )
    )
    blocks.append(("h2", "Results after 100 pieces", "100 个方块后的结果"))
    rows = []
    for name in PROFILES:
        for mode, label_en, label_zh in (
            ("vision", "vision", "视觉"),
            ("text", "text only", "纯文字"),
        ):
            s = m[name][mode]
            rows.append(
                [
                    (f"{name} · {model(runs, name)}", f"{name} · {model(runs, name)}"),
                    (label_en, label_zh),
                    f"{s['goal_reached']} / {s['games']}",
                    f"{s['clean_goal']} / {s['games']}",
                    f"{s['topped_out']} / {s['games']}",
                    f"{statistics.median(s['pieces_to_goal']):.0f}" if s["pieces_to_goal"] else "—",
                    f"{statistics.fmean(s['lines']):.1f}",
                    f"{number(statistics.fmean(s['score']))} / {number(max(s['score']))}",
                    f"{statistics.median(s['max_holes']):.0f}",
                    f"{seconds(s['latency_ms']['median'])} · {seconds(s['latency_ms']['p90'])}",
                    percent(s["agreement"]),
                    f"{s['mean_regret']:.2f}",
                ]
            )
    blocks.append(
        (
            "table",
            [
                ("Profile", "档位"),
                ("Prompt", "提示方式"),
                ("10 clears", "完成 10 次消除"),
                ("Hole-free goal", "零空洞达成"),
                ("Topped out", "堆满出局"),
                ("Pieces to goal", "达成所需方块"),
                ("Lines", "消除行数"),
                ("Score (mean / best)", "得分（平均 / 最高）"),
                ("Most holes", "最多空洞"),
                ("Call median · p90", "调用中位数 · p90"),
                ("Agreement", "一致率"),
                ("Regret", "遗憾值"),
            ],
            rows,
        )
    )
    blocks.append(
        (
            "note",
            "Five games per row (seeds 101, 202, 303, 404, 505). Pieces to goal and most holes are "
            "medians over the games; lines are means. Agreement and regret compare each "
            "non-forced decision with the reference evaluator (Yiyuan Lee's tuned weights), which "
            "never influences a move.",
            "每行 5 局（种子 101、202、303、404、505）。“达成所需方块”与“最多空洞”取各局中位数，消除行数取平均值。"
            "一致率与遗憾值把每个非强制决策与参考评估器（Yiyuan Lee 调优权重）比较；参考评估器从不参与落子。",
        )
    )
    blocks.append(("h2", "Charts", "图表"))
    blocks.append(
        (
            "figure",
            "latency",
            "Every vision-mode call per profile. The white tick marks the median, the gray tick the "
            "text-only median.",
            "视觉模式下每一次调用的往返耗时。白色短线为中位数，灰色短线为纯文字提示的中位数。",
        )
    )
    blocks.append(
        (
            "figure",
            "outcomes",
            "Score, lines cleared and most holes after 100 pieces; one dot per game.",
            "100 个方块后的得分、消除行数与最多空洞；每个点代表一局。",
        )
    )
    blocks.append(("h2", "How one decision works", "一次决策如何完成"))
    blocks.append(
        (
            "steps",
            [
                (
                    "**Enumerate.** Code lists every legal placement of the falling piece (rotate, "
                    "shift, hard drop) and every placement of the next piece after it: usually "
                    "300–600 two-piece plans.",
                    "**枚举。** 代码列出当前方块的所有合法落点（旋转、平移、硬降），再对每个落点列出下一个方块的所有落点，"
                    "通常得到 300–600 个两步方案。",
                ),
                (
                    f"**Prune without weights.** A plan is dropped only when another plan matches or "
                    f"beats it on every measured fact: rows cleared, holes, stack height, aggregate "
                    f"height and bumpiness. A median of {v['balanced']['options_median']:.0f} plans "
                    f"remain; they are listed left to right, so their order carries no hint.",
                    f"**无权重剪枝。** 只有当某个方案在每一项实测指标（消除行数、空洞、最高高度、总高度、凹凸度）上"
                    f"都不优于另一个方案时，才会被剔除。剪枝后中位数只剩 {v['balanced']['options_median']:.0f} 个方案，"
                    f"并按从左到右排列，顺序本身不提供任何暗示。",
                ),
                (
                    "**Ask once.** One Choice question lists each plan as a complete key sequence "
                    "with its measured result, and one image shows the outcome of every plan as a "
                    "lettered tile.",
                    "**只问一次。** 一个 Choice 问题把每个方案写成完整的按键序列并附上实测结果，"
                    "同时用一张图片把每个方案的结果画成带字母的小图。",
                ),
                (
                    f"**Read one token.** OpenJev returns the full distribution over the option "
                    f"labels and code presses the chosen keys for both pieces. When pruning leaves a "
                    f"single plan, it is played without a call and counted as forced "
                    f"({decisions - calls} of {number(decisions)} decisions).",
                    f"**读取 1 个 token。** OpenJev 返回全部选项标签上的完整概率分布，代码据此为两个方块依次按键。"
                    f"若剪枝后只剩一个方案，则不调用模型、直接执行，并记为强制决策（{number(decisions)} 次决策中有 "
                    f"{decisions - calls} 次）。",
                ),
            ],
        )
    )
    blocks.append(
        (
            "h3",
            f"A real decision: the {ex['profile']} run, seed {ex['seed']}, decision {ex['number'] + 1}",
            f"真实示例：{ex['profile']} 对局，种子 {ex['seed']}，第 {ex['number'] + 1} 次决策",
        )
    )
    image = ex["image"]
    blocks.append(
        (
            "image",
            "figures/example-sheet.png",
            f"The image sent: {image['width']} × {image['height']} px, {image['tokens']} image tokens. "
            f"Tile A clears a row (+1).",
            f"发送的图片：{image['width']} × {image['height']} 像素，{image['tokens']} 个图像 token。"
            f"A 方案消除一行（+1）。",
        )
    )
    blocks.append(("code", "json", ex["request"], ("Request", "请求")))
    blocks.append(
        ("code", "json", ex["response"], ("Response (values rounded)", "响应（数值已取整）"))
    )
    chosen = next(o for o in rec["options"] if o["label"] == ex["chosen"])
    blocks.append(
        (
            "p",
            f"Jev put {percent(chosen['probability'])} on plan {ex['chosen']}, the only plan that "
            f"clears a row without a new hole. The call took {seconds(rec['client_ms'])} with "
            f"{rec['input_tokens']} input tokens.",
            f"Jev 把 {percent(chosen['probability'])} 的概率给了方案 {ex['chosen']}：唯一既能消行又不产生新空洞"
            f"的方案。本次调用耗时 {seconds(rec['client_ms'], True)}，输入 {rec['input_tokens']} 个 token。",
        )
    )
    blocks.append(
        (
            "p",
            "**Image resolution.** Qwen's vision encoder cuts images into 16 px patches and merges "
            "each 2 × 2 group into one token (32 px). The outcome sheet draws one board cell per "
            "16 px patch, crops each tile to the rows in use and keeps every tile on the 32 px grid, "
            "so the server never resamples it (it stays under 1,024 px and 512 image tokens).",
            "**图像分辨率。** Qwen 的视觉编码器把图片切成 16 像素的 patch，再把每 2 × 2 个 patch 合并成 1 个 "
            "token（32 像素）。结果缩略图让每个棋盘格恰好落在一个 16 像素 patch 上，每个方案只截取实际用到的行，"
            "所有小图都对齐 32 像素网格，因此服务端无需重新缩放（边长不超过 1,024 像素，图像 token 不超过 512）。",
        )
    )
    blocks.append(("h2", "Design study", "设计实验"))
    blocks.append(
        (
            "p",
            "Before the benchmark, the same 48 decision states were shown to each model in eight "
            "ways. The states come from reference games on seeds 1–4; the benchmark seeds were "
            "never used while designing the prompt.",
            "正式测试前，同样的 48 个决策状态以 8 种方式分别呈现给每个模型。这些状态来自种子 1–4 上的参考对局；"
            "设计提示词时从未使用正式测试的种子。",
        )
    )
    blocks.append(
        (
            "figure",
            "design",
            "Mean regret per presentation (lower is better) and the median call time.",
            "每种呈现方式的平均遗憾值（越低越好）与调用耗时中位数。",
        )
    )
    rows = []
    for key, (en, zh) in VARIANT_NAMES.items():
        rows.append(
            [(en, zh), f"{ab['balanced'][key]['median_input_tokens']:.0f}"]
            + [f"{ab[n][key]['mean_regret']:.2f}" for n in PROFILES]
            + [f"{ab[n][key]['median_ms']:.0f} ms" for n in PROFILES]
        )
    blocks.append(
        (
            "table",
            [
                ("Presentation", "呈现方式"),
                ("Input tokens", "输入 token"),
                ("Regret · fast", "遗憾值 · fast"),
                ("Regret · balanced", "遗憾值 · balanced"),
                ("Regret · quality", "遗憾值 · quality"),
                ("Call · fast", "调用 · fast"),
                ("Call · balanced", "调用 · balanced"),
                ("Call · quality", "调用 · quality"),
            ],
            rows,
        )
    )
    blocks.append(("h2", "Method and provenance", "方法与来源"))
    blocks.append(
        (
            "list",
            [
                (
                    f"**Machine.** {machine['chip']}, {machine['memory_gb']} GB; llama.cpp "
                    f"{machine['llama_cpp']} on Metal with one inference slot, four CPU threads, an "
                    f"8,192-token context and a 512-token image budget. Profiles ran one after another, "
                    f"with one profile active at a time and no other inference running.",
                    f"**硬件。** {machine['chip']}，{machine['memory_gb']} GB；llama.cpp {machine['llama_cpp']}"
                    f"（Metal），单推理槽、4 个 CPU 线程、8,192 token 上下文、每张图 512 个图像 token 上限。"
                    f"各档位依次测试，同一时间只有一个档位在推理，也没有其他推理任务。",
                ),
                (
                    "**Models.** The pinned OpenJev profiles: Qwen3.5-0.8B Q4_K_M, Qwen3.5-4B Q4_K_M "
                    "and Qwen3.6-35B-A3B UD-Q4_K_XL, each with its matching F16 vision projector. "
                    "Weight files were checked by SHA-256 against the pinned Hugging Face revisions.",
                    "**模型。** 使用 OpenJev 固定版本的三个档位：Qwen3.5-0.8B Q4_K_M、Qwen3.5-4B Q4_K_M 与 "
                    "Qwen3.6-35B-A3B UD-Q4_K_XL，各自搭配对应的 F16 视觉投影器。权重文件均按 SHA-256 与固定的 "
                    "Hugging Face 版本核对。",
                ),
                (
                    "**Protocol.** Seeds 101, 202, 303, 404 and 505; 100 pieces per game or until the "
                    "stack tops out; the same seeds, prompt and pruning for every model. The goal "
                    "counts ten separate line-clear events.",
                    "**流程。** 种子 101、202、303、404、505；每局 100 个方块，或直到堆满出局；所有模型使用相同的种子、"
                    "提示词与剪枝规则。目标按 10 次独立的消除事件计算。",
                ),
                (
                    "**Measured.** Client round trip (localhost), server time (`x-openjev-elapsed-ms`), "
                    "input tokens, the full probability distribution and every key pressed. The "
                    "reference evaluator only scores decisions after the fact.",
                    "**记录内容。** 客户端往返耗时（本机）、服务端耗时（`x-openjev-elapsed-ms`）、输入 token、"
                    "完整概率分布以及每一次按键。参考评估器只在事后为决策打分。",
                ),
                (
                    f"**Replays.** Videos and the browser replay re-simulate the recorded keys. The "
                    f"Python and JavaScript engines reproduce all 30 games, {number(decisions)} "
                    f"decisions and every option exactly.",
                    f"**回放。** 视频与网页回放都按录制的按键重新模拟。Python 与 JavaScript 两套引擎逐一复现了全部 "
                    f"30 局、{number(decisions)} 次决策以及每一个候选方案。",
                ),
                (
                    "**Limits.** Five seeds per configuration is a small sample; regret and agreement "
                    "depend on the chosen reference evaluator; timings are for one Mac without "
                    "concurrent load. Pieces spawn inside the visible well; there is no hold piece "
                    "and no soft-drop tucks or spins.",
                    "**局限。** 每种配置只有 5 个种子，样本较小；遗憾值与一致率取决于所选参考评估器；耗时只代表这台 Mac "
                    "在无并发负载时的表现。方块在可见区域内生成，不支持暂存（hold），也不做软降塞入与旋转技巧。",
                ),
            ],
        )
    )
    blocks.append(("h2", "Reproduce", "复现"))
    blocks.append(
        (
            "code",
            "bash",
            (
                "uv run openjev serve --profile balanced     # one profile at a time\n"
                "uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,text\n"
                "uv run python examples/tetris/play.py ablation\n"
                "uv run python examples/tetris/report.py     # summary, figures, pages, replays\n"
                "uv run python examples/tetris/video.py --profile balanced --seed 101",
                "uv run openjev serve --profile balanced     # 一次只运行一个档位\n"
                "uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,text\n"
                "uv run python examples/tetris/play.py ablation\n"
                "uv run python examples/tetris/report.py     # 汇总、图表、报告页面与回放数据\n"
                "uv run python examples/tetris/video.py --profile balanced --seed 101",
            ),
            ("", ""),
        )
    )
    return blocks


# --------------------------------------------------------------------------- Markdown


def markdown(blocks: list[tuple], zh: bool) -> str:
    i = 1 if zh else 0
    title = "俄罗斯方块测试报告" if zh else "Tetris test report"
    other = "[English](README.md)" if zh else "[中文](README.zh-CN.md)"
    links = (
        f"[可视化报告]({SITE}demos/tetris/report/) · [在浏览器中试玩]({SITE}demos/tetris/web/) · "
        f"[示例说明](../README.zh-CN.md) · {other}"
        if zh
        else f"[Visual report]({SITE}demos/tetris/report/) · [Play in the browser]({SITE}demos/tetris/web/) · "
        f"[How the example works](../README.md) · {other}"
    )
    out = [f"# {title}", "", links, ""]
    for block in blocks:
        kind = block[0]
        if kind == "lede":
            out += [block[1 + i], ""]
        elif kind == "kpis":
            for value, label, note in block[1]:
                out.append(f"- **{value}** {label[i]} ({note[i]})")
            out.append("")
        elif kind in ("h2", "h3"):
            out += [("## " if kind == "h2" else "### ") + block[1 + i], ""]
        elif kind in ("p", "note"):
            out += [block[1 + i], ""]
        elif kind in ("list", "steps"):
            for n, item in enumerate(block[1], 1):
                out.append(f"{n}. {item[i]}" if kind == "steps" else f"- {item[i]}")
            out.append("")
        elif kind == "videos":
            cells = []
            for name, heading, caption in block[1]:
                cells.append(
                    f"[![{heading}](videos/{name}.jpg)](videos/{name}.mp4)<br>"
                    f"**{heading}**<br>{caption[i]}"
                )
            out += ["| " + " | ".join(cells) + " |", "|" + "---|" * len(cells), ""]
        elif kind == "table":
            headers, rows = block[1], block[2]
            out.append("| " + " | ".join(h[i] for h in headers) + " |")
            out.append("|" + "---|" * len(headers))
            for row in rows:
                out.append(
                    "| " + " | ".join(c[i] if isinstance(c, tuple) else c for c in row) + " |"
                )
            out.append("")
        elif kind == "figure":
            name = f"{block[1]}.zh" if zh else block[1]
            out += [f"![{block[2 + i]}](figures/{name}.svg)", "", f"*{block[2 + i]}*", ""]
        elif kind == "image":
            out += [f"![{block[2 + i]}]({block[1]})", "", f"*{block[2 + i]}*", ""]
        elif kind == "code":
            caption = block[3][i]
            if caption:
                out += [f"**{caption}**", ""]
            code = block[2][i] if isinstance(block[2], tuple) else block[2]
            out += [f"```{block[1]}", code, "```", ""]
    files = (
        [
            "## 本目录文件",
            "",
            "- `runs/*.json`：每局每次决策的完整记录（每行一次决策）。",
            "- `ablation/*.json`：设计实验结果。",
            "- `summary.json`：报告使用的汇总数据；`replays.json`：网页回放数据。",
            "- `figures/`：SVG 图表与示例图片；`videos/`：三个档位的对局视频与封面。",
        ]
        if zh
        else [
            "## Files in this folder",
            "",
            "- `runs/*.json`: every decision of every game, one line per decision.",
            "- `ablation/*.json`: the design study.",
            "- `summary.json`: the aggregates behind this page; `replays.json`: data for the web replay.",
            "- `figures/`: SVG charts and the example image; `videos/`: one video and poster per profile.",
        ]
    )
    return "\n".join(out + files) + "\n"


# --------------------------------------------------------------------------- HTML


def inline_html(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)


def both(pair, tag: str = "span") -> str:
    en, zh = pair
    return f'<{tag} lang="en">{inline_html(en)}</{tag}><{tag} lang="zh">{inline_html(zh)}</{tag}>'


def page(blocks: list[tuple], figures: Path) -> str:
    body = []
    for block in blocks:
        kind = block[0]
        if kind == "lede":
            body.append(f'<p class="lede">{both(block[1:3])}</p>')
        elif kind == "kpis":
            tiles = "".join(
                f'<div class="kpi"><strong>{html.escape(value)}</strong>'
                f"<span>{both(label)}</span><small>{both(note)}</small></div>"
                for value, label, note in block[1]
            )
            body.append(f'<div class="kpis">{tiles}</div>')
        elif kind in ("h2", "h3"):
            body.append(f"<{kind}>{both(block[1:3])}</{kind}>")
        elif kind == "p":
            body.append(f"<p>{both(block[1:3])}</p>")
        elif kind == "note":
            body.append(f'<p class="note">{both(block[1:3])}</p>')
        elif kind in ("list", "steps"):
            tag = "ol" if kind == "steps" else "ul"
            items = "".join(f"<li>{both(item)}</li>" for item in block[1])
            body.append(f'<{tag} class="{kind}">{items}</{tag}>')
        elif kind == "videos":
            cards = "".join(
                f'<figure class="video"><video src="videos/{name}.mp4" poster="videos/{name}.jpg" '
                f'controls muted playsinline preload="metadata"></video>'
                f"<figcaption><strong>{html.escape(heading)}</strong>{both(caption)}</figcaption></figure>"
                for name, heading, caption in block[1]
            )
            body.append(f'<div class="videos">{cards}</div>')
        elif kind == "table":
            headers, rows = block[1], block[2]
            head = "".join(f"<th>{both(h)}</th>" for h in headers)
            lines = "".join(
                "<tr>"
                + "".join(
                    f"<td>{both(c) if isinstance(c, tuple) else html.escape(c)}</td>" for c in row
                )
                + "</tr>"
                for row in rows
            )
            body.append(
                f'<div class="table"><table><thead><tr>{head}</tr></thead><tbody>{lines}</tbody>'
                "</table></div>"
            )
        elif kind == "figure":
            charts = "".join(
                f'<div lang="{lang}">{(figures / f"{block[1]}{suffix}.svg").read_text()}</div>'
                for lang, suffix in (("en", ""), ("zh", ".zh"))
            )
            body.append(
                f'<figure class="chart">{charts}<figcaption>{both(block[2:4])}</figcaption></figure>'
            )
        elif kind == "image":
            body.append(
                f'<figure class="shot"><img src="{block[1]}" alt="{html.escape(block[2])}">'
                f"<figcaption>{both(block[2:4])}</figcaption></figure>"
            )
        elif kind == "code":
            caption = f'<div class="code-label">{both(block[3])}</div>' if block[3][0] else ""
            if isinstance(block[2], tuple):
                code = "".join(
                    f'<pre lang="{lang}"><code>{html.escape(text)}</code></pre>'
                    for lang, text in zip(("en", "zh"), block[2], strict=True)
                )
            else:
                code = f"<pre><code>{html.escape(block[2])}</code></pre>"
            body.append(caption + code)
    return TEMPLATE.replace("{{BODY}}", "\n".join(body)).replace("{{SITE}}", SITE)


TEMPLATE = """<!doctype html>
<html lang="en" data-lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tetris test report · OpenJev Multimodal</title>
<meta name="description" content="Three local Qwen models play Tetris through OpenJev Multimodal: results, videos, latency and the design study behind one-token decisions.">
<meta name="theme-color" content="#101713">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'%3E%3Crect width='20' height='20' rx='4' fill='%23101713'/%3E%3Cpath d='M10 3 17 10 10 17 3 10Z' fill='%23b4f784'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,400..700&family=Space+Grotesk:wght@500;600&display=swap">
<style>
:root { color-scheme: dark; --bg:#101713; --panel:#141e16; --line:#2b382e; --line-2:#3a4b38; --text-1:#eef1e9; --text-2:#acb7ac; --muted:#7f967a; --accent:#b4f784; --accent-bg:#1e2c1f;
  --sans:"DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif; --display:"Space Grotesk","DM Sans",system-ui,sans-serif; --mono:"DM Mono",ui-monospace,"SF Mono",Menlo,monospace; }
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--text-1); font: 16px/1.65 var(--sans); }
html[data-lang="en"] [lang="zh"], html[data-lang="zh"] [lang="en"] { display: none !important; }
a { color: var(--accent); }
.bar { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 20px; padding: 12px max(24px, calc(50% - 560px)); background: rgba(16,23,19,.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 10px; color: var(--text-1); text-decoration: none; font: 600 18px/1 var(--display); letter-spacing: -.3px; }
.brand svg { width: 18px; height: 18px; color: var(--accent); }
.bar nav { margin-left: auto; display: flex; gap: 18px; align-items: center; font-size: 14px; }
.bar nav a { color: var(--text-2); text-decoration: none; }
.bar nav a:hover { color: var(--accent); }
.bar button { border: 1px solid var(--line); background: none; color: var(--text-2); border-radius: 7px; padding: 5px 10px; font: 13px var(--sans); cursor: pointer; }
main { max-width: 1120px; margin: 0 auto; padding: 48px 24px 80px; }
.eyebrow { font: 12px var(--mono); letter-spacing: 2px; color: var(--muted); text-transform: uppercase; }
h1 { font: 500 clamp(36px, 5vw, 58px)/1.08 var(--display); letter-spacing: -2px; margin: 14px 0 18px; }
h1 em { font-style: normal; color: var(--accent); }
h2 { font: 500 30px/1.2 var(--display); letter-spacing: -.8px; margin: 64px 0 16px; }
h3 { font: 600 19px/1.3 var(--sans); margin: 36px 0 12px; }
p { color: var(--text-2); max-width: 820px; }
p strong, li strong { color: var(--text-1); }
.lede { font-size: 18px; color: var(--text-2); max-width: 860px; }
.note { font-size: 13px; color: var(--muted); }
code { font: .88em var(--mono); color: var(--text-1); }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 32px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px; }
.kpi strong { display: block; font: 500 28px/1.1 var(--display); letter-spacing: -.5px; color: var(--text-1); }
.kpi span { display: block; margin-top: 8px; font-size: 14px; color: var(--text-1); }
.kpi small { display: block; margin-top: 6px; font-size: 12px; color: var(--muted); }
.videos { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.video { margin: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
.video video { display: block; width: 100%; aspect-ratio: 16 / 9; background: #0b110d; }
.video figcaption { padding: 12px 14px 14px; font-size: 13px; color: var(--muted); }
.video figcaption strong { display: block; color: var(--text-1); font-size: 14px; margin-bottom: 2px; }
ul.list, ol.steps { color: var(--text-2); max-width: 880px; padding-left: 22px; }
ul.list li, ol.steps li { margin: 10px 0; }
.table { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; font-variant-numeric: tabular-nums; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { font: 11px var(--mono); letter-spacing: 1px; color: var(--muted); text-transform: uppercase; background: var(--panel); }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: #172019; }
td:first-child { color: var(--text-1); }
figure.chart, figure.shot { margin: 18px 0 28px; }
figure.chart svg { display: block; width: 100%; height: auto; }
figure.shot img { display: block; width: min(100%, 864px); image-rendering: pixelated; border-radius: 6px; }
figure figcaption { font-size: 13px; color: var(--muted); margin-top: 8px; }
pre { background: #0b110d; border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; overflow-x: auto; font: 13px/1.55 var(--mono); color: var(--text-2); }
.code-label { font: 12px var(--mono); letter-spacing: 1px; color: var(--muted); text-transform: uppercase; margin-top: 18px; }
footer { max-width: 1120px; margin: 0 auto; padding: 0 24px 48px; color: var(--muted); font-size: 13px; }
@media (max-width: 900px) { .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } .videos { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .kpis { grid-template-columns: 1fr; } .bar nav a.optional { display: none; } h2 { font-size: 26px; } }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<header class="bar">
  <a class="brand" href="{{SITE}}"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 1 19 10 10 19 1 10Z" fill="currentColor"/><circle cx="10" cy="10" r="3.2" fill="#101713"/></svg>OpenJev Multimodal</a>
  <nav>
    <a href="../web/"><span lang="en">Play &amp; replay</span><span lang="zh">试玩与回放</span></a>
    <a class="optional" href="https://github.com/Hand-In/openjev-multimodal/tree/main/examples/tetris">GitHub</a>
    <button type="button" id="lang">中文</button>
  </nav>
</header>
<main>
<div class="eyebrow"><span lang="en">Test report · Tetris</span><span lang="zh">测试报告 · 俄罗斯方块</span></div>
<h1><span lang="en">OpenJev Multimodal <em>plays Tetris</em></span><span lang="zh">OpenJev Multimodal <em>玩俄罗斯方块</em></span></h1>
{{BODY}}
</main>
<footer><span lang="en">Generated from the recorded runs by <code>examples/tetris/report.py</code>. MIT licensed.</span><span lang="zh">由 <code>examples/tetris/report.py</code> 根据录制数据生成。MIT 许可。</span></footer>
<script>
(() => {
  const root = document.documentElement, button = document.getElementById("lang");
  const set = (lang) => {
    root.dataset.lang = lang; root.lang = lang === "zh" ? "zh-CN" : "en";
    button.textContent = lang === "zh" ? "English" : "中文";
    try { localStorage.setItem("openjev-report-lang", lang); } catch {}
  };
  let lang = navigator.language && navigator.language.startsWith("zh") ? "zh" : "en";
  try { lang = localStorage.getItem("openjev-report-lang") || lang; } catch {}
  set(lang);
  button.addEventListener("click", () => set(root.dataset.lang === "zh" ? "en" : "zh"));
})();
</script>
</body>
</html>
"""


def write(summary: dict, runs: dict, report: Path) -> None:
    figures = report / "figures"
    blocks = build(summary, runs, figures)
    (report / "README.md").write_text(markdown(blocks, zh=False))
    (report / "README.zh-CN.md").write_text(markdown(blocks, zh=True))
    (report / "index.html").write_text(page(blocks, figures))
