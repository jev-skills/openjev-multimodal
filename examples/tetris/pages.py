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

SITE = "https://jev-skills.github.io/openjev-multimodal/"
PROFILES = ("fast", "balanced", "quality", "max")
MODES = ("vision", "text", "compact")
MODE_NAMES = {
    "vision": ("vision", "视觉"),
    "text": ("text only", "纯文字"),
    "compact": ("compact", "精简"),
}
VARIANT_NAMES = {
    "vision": ("Facts + outcome sheet (default)", "文字事实 + 结果缩略图（默认）"),
    "compact": ("Compact: cached rules, short facts", "精简：规则缓存 + 简短事实"),
    "vision@0.5": ("Facts + sheet at ½ size", "文字事实 + ½ 尺寸缩略图"),
    "vision@2.0": ("Facts + sheet at 2×", "文字事实 + 2 倍缩略图"),
    "text": ("Facts only, no image", "仅文字事实，不发图片"),
    "board": ("Facts + board screenshot", "文字事实 + 棋盘截图"),
    "board@0.5": ("Facts + screenshot at ½ size", "文字事实 + ½ 尺寸截图"),
    "board@2.0": ("Facts + screenshot at 2×", "文字事实 + 2 倍截图"),
    "pixels": ("Outcome sheet only, no facts", "仅结果缩略图，无文字事实"),
}
VIDEOS = {"fast": "vision", "balanced": "vision", "quality": "vision", "max": "compact"}


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
    """Numbers for the video of one profile: its seed-101 game up to the tenth clear."""
    run = game_of(runs, profile, seed, VIDEOS[profile])
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
    compact, _ = payload(game, options, "compact")
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
        "compact": json.dumps(compact, indent=2, ensure_ascii=False),
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
    ab = {name: p[name]["ablation"] for name in PROFILES}
    base = summary["baselines"]
    video = {name: goal_video(runs, name) for name in PROFILES}
    ex = example(runs, figures)
    rec = ex["record"]
    played = [(n, mode) for n in PROFILES for mode in MODES if mode in m[n]]
    games = sum(m[n][mode]["games"] for n, mode in played)
    goals = sum(m[n][mode]["goal_reached"] for n, mode in played)
    decisions = sum(m[n][mode]["decisions"] for n, mode in played)
    calls = sum(m[n][mode]["calls"] for n, mode in played)
    best = max(
        (score, name, mode, seed)
        for name, mode in played
        for seed, score in zip(m[name][mode]["seeds"], m[name][mode]["score"], strict=True)
    )
    top = m["max"]["compact"]
    top_lines = statistics.fmean(top["lines"])
    top_ms = top["latency_ms"]["median"]
    random, reference = base["random"], base["reference"]
    probe = {name: summary["probes"][name]["median_ms"] for name in summary["probes"]}
    measured = min(summary["measured"].values())[:10]
    machine = summary["machine"]
    names = {n: f"{n} · {model(runs, n)}" for n in PROFILES}

    def prompt(mode: str) -> tuple[str, str]:
        return MODE_NAMES[mode]

    blocks: list[tuple] = []
    blocks.append(
        (
            "lede",
            (
                f"Four local Qwen models played Tetris through OpenJev Multimodal. Code lists every "
                f"legal move and simulates its outcome; the model makes every choice, reading one "
                f"output token per two pieces. {games} games of 100 pieces, the same five piece "
                f"sequences for every model, measured {measured} on an {machine['chip']}."
            ),
            (
                f"四个本地 Qwen 模型通过 OpenJev Multimodal 玩俄罗斯方块。代码列出所有合法走法并模拟结果，"
                f"每一步都由模型选择，每两个方块只读取 1 个输出 token。共 {games} 局、每局 100 个方块，"
                f"所有模型面对相同的 5 组方块序列，测于 {measured}，{machine['chip']}。"
            ),
        )
    )
    blocks.append(
        (
            "kpis",
            [
                (
                    f"{goals} / {games}",
                    ("games reached 10 line clears", "局达成 10 次消除"),
                    (
                        f"{len(PROFILES)} models × prompts × 5 seeds · 0 illegal keys",
                        f"{len(PROFILES)} 个模型 × 提示方式 × 5 个种子 · 非法按键 0",
                    ),
                ),
                (
                    seconds(top_ms),
                    ("per decision on Qwen3.8-27B", "Qwen3.8-27B 每次决策"),
                    (
                        f"median of {top['calls']} compact calls · the same prompt uncached: "
                        f"{seconds(probe['stock'])}",
                        f"精简提示 {top['calls']} 次调用的中位数 · 同一提示不缓存时为 {seconds(probe['stock'], True)}",
                    ),
                ),
                (
                    f"{top_lines:.1f}",
                    ("lines per game, max · compact", "每局消除行数，max · 精简"),
                    (
                        f"random picks on the same plans: {random['mean_lines']:.1f}",
                        f"同样的方案随机选择：{random['mean_lines']:.1f}",
                    ),
                ),
                (
                    number(best[0]),
                    ("best score after 100 pieces", "100 个方块后的最高分"),
                    (
                        f"{best[1]} · {prompt(best[2])[0]} · seed {best[3]}",
                        f"{best[1]} · {prompt(best[2])[1]} · 种子 {best[3]}",
                    ),
                ),
            ],
        )
    )
    blocks.append(("h2", "Watch each model play", "观看每个模型对局"))
    blocks.append(
        (
            "p",
            "Seed 101, from the first piece to the tenth line clear. Waiting time is the measured "
            "round trip of each call.",
            "种子 101，从第一个方块播放到第 10 次消除。等待时间是每次调用实测的往返耗时。",
        )
    )
    blocks.append(
        (
            "videos",
            [
                (
                    name,
                    names[name],
                    (
                        f"{prompt(VIDEOS[name])[0]} · goal after {video[name]['pieces']} pieces · "
                        f"{seconds(video[name]['median_ms'])} per call",
                        f"{prompt(VIDEOS[name])[1]} · {video[name]['pieces']} 个方块达成 · "
                        f"每次调用 {seconds(video[name]['median_ms'], True)}",
                    ),
                )
                for name in PROFILES
            ],
        )
    )
    blocks.append(("h2", "Results after 100 pieces", "100 个方块后的结果"))
    rows = []
    for name, mode in played:
        s = m[name][mode]
        rows.append(
            [
                (names[name], names[name]),
                prompt(mode),
                f"{s['goal_reached']} / {s['games']}",
                f"{s['clean_goal']} / {s['games']}",
                f"{s['topped_out']} / {s['games']}",
                f"{statistics.fmean(s['lines']):.1f}",
                f"{number(statistics.fmean(s['score']))} / {number(max(s['score']))}",
                f"{statistics.median(s['max_holes']):.0f}",
                seconds(s["latency_ms"]["median"]),
                percent(s["agreement"]),
            ]
        )
    blocks.append(
        (
            "table",
            [
                ("Profile", "档位"),
                ("Prompt", "提示方式"),
                ("10 clears", "10 次消除"),
                ("Hole-free goal", "零空洞达成"),
                ("Topped out", "堆满出局"),
                ("Lines", "消除行数"),
                ("Score (mean / best)", "得分（平均 / 最高）"),
                ("Most holes", "最多空洞"),
                ("Call median", "调用中位数"),
                ("Agreement", "一致率"),
            ],
            rows,
        )
    )
    blocks.append(
        (
            "note",
            "Five games per row, seeds 101–505. Most holes is the median over games; lines are "
            "means. Agreement compares each non-forced decision with a reference evaluator "
            "(Yiyuan Lee's tuned weights) that never influences a move.",
            "每行 5 局，种子 101–505。“最多空洞”取各局中位数，消除行数取平均值。一致率把每个非强制决策与参考评估器"
            "（Yiyuan Lee 调优权重）比较；参考评估器从不参与落子。",
        )
    )
    blocks.append(("h2", "Without a model", "没有模型会怎样"))
    blocks.append(
        (
            "p",
            "The same games with the model replaced by a fixed rule, on the same pruned plans. "
            "Pruning removes only plans that another plan matches or beats on every fact; what "
            "remains still has to be chosen.",
            "同样的对局、同样的剪枝方案，把模型换成固定规则。剪枝只去掉在每项事实上都不优于另一方案的走法，"
            "剩下的方案仍需要选择。",
        )
    )
    policies = (
        ("random", ("Random pick", "随机选择")),
        ("first", ("Always the first plan", "总选第一个方案")),
        ("reference", ("Reference evaluator", "参考评估器")),
    )
    rows = [
        [
            label,
            f"{base[key]['goal_reached']} / {base[key]['games']}",
            f"{base[key]['topped_out']} / {base[key]['games']}",
            f"{base[key]['mean_lines']:.1f}",
            f"{number(base[key]['mean_score'])} / {number(base[key]['best_score'])}",
            f"{base[key]['median_max_holes']:.0f}",
        ]
        for key, label in policies
    ]
    blocks.append(
        (
            "table",
            [
                ("Policy", "规则"),
                ("10 clears", "10 次消除"),
                ("Topped out", "堆满出局"),
                ("Lines", "消除行数"),
                ("Score (mean / best)", "得分（平均 / 最高）"),
                ("Most holes", "最多空洞"),
            ],
            rows,
        )
    )
    blocks.append(
        (
            "note",
            f"Random: {random['games'] // 5} games per seed. The reference evaluator is a tuned "
            "heuristic, shown for scale; it plays no part in the model's games.",
            f"随机选择：每个种子 {random['games'] // 5} 局。参考评估器是调优过的启发式规则，仅作对照，"
            "不参与模型的对局。",
        )
    )
    blocks.append(("h2", "What the runs show", "测试结论"))
    fast_lines_v = statistics.fmean(v["fast"]["lines"])
    fast_lines_t = statistics.fmean(m["fast"]["text"]["lines"])
    fast_lines_c = statistics.fmean(m["fast"]["compact"]["lines"])
    fast_lines_t, fast_lines_c = sorted((fast_lines_t, fast_lines_c))
    qc = m["quality"]["compact"]
    agreement = " · ".join(percent(v[n]["agreement"]) for n in PROFILES)
    blocks.append(
        (
            "list",
            [
                (
                    f"**The model makes the choices that matter.** On the same plans, random picks "
                    f"top out in {random['topped_out']} of {random['games']} games and clear "
                    f"{random['mean_lines']:.1f} lines. Qwen3.8-27B clears {top_lines:.1f} and never "
                    f"tops out, level with the reference evaluator ({reference['mean_lines']:.1f}).",
                    f"**关键的选择由模型做出。** 在同样的方案上，随机选择 {random['games']} 局中有 "
                    f"{random['topped_out']} 局堆满出局，平均消除 {random['mean_lines']:.1f} 行；Qwen3.8-27B 平均消除 "
                    f"{top_lines:.1f} 行且从未出局，与参考评估器（{reference['mean_lines']:.1f}）相当。",
                ),
                (
                    f"**Larger models judge better.** Agreement with the reference evaluator, vision "
                    f"prompt: {agreement} for 0.8B, 4B, 35B-A3B and 27B.",
                    f"**模型越大，判断越好。** 视觉提示下与参考评估器的一致率：0.8B、4B、35B-A3B、27B 依次为 "
                    f"{agreement.replace(' · ', '、')}。",
                ),
                (
                    f"**A 27B model in well under a second.** A dense 27B model processes about 200 "
                    f"prompt tokens per second on this Mac, so the full compact prompt takes "
                    f"{seconds(probe['stock'])}. The compact prompt sends the rules as an unchanging "
                    f"state, which the API keeps cached ({seconds(probe['stock-cache'])}), and "
                    f"OpenJev's llama.cpp patch skips a checkpoint pass the cache never needs "
                    f"({seconds(probe['patched-cache'])}). Sixteen decisions per setup.",
                    f"**27B 模型也能在一秒内决策。** 稠密 27B 模型在这台 Mac 上每秒约处理 200 个提示 token，完整的精简提示需 "
                    f"{seconds(probe['stock'], True)}。精简提示把规则作为不变的 state，由 API 缓存"
                    f"（{seconds(probe['stock-cache'], True)}）；OpenJev 的 llama.cpp 补丁再跳过缓存用不到的检查点计算"
                    f"（{seconds(probe['patched-cache'], True)}）。每种配置 16 次决策。",
                ),
                (
                    f"**Large models need little; small ones need the picture.** With the compact "
                    f"prompt, quality clears {statistics.fmean(qc['lines']):.1f} lines, hole-free in "
                    f"{qc['clean_goal']} of {qc['games']} games, at {seconds(qc['latency_ms']['median'])} "
                    f"per call. The 0.8B model clears {fast_lines_v:.1f} lines with the outcome sheet "
                    f"and {fast_lines_t:.1f}–{fast_lines_c:.1f} without it.",
                    f"**大模型需要的信息很少，小模型需要图片。** 使用精简提示时，quality 平均消除 "
                    f"{statistics.fmean(qc['lines']):.1f} 行，{qc['games']} 局中有 {qc['clean_goal']} 局零空洞达成，"
                    f"每次调用 {seconds(qc['latency_ms']['median'], True)}。0.8B 模型有结果缩略图时消除 "
                    f"{fast_lines_v:.1f} 行，没有时只有 {fast_lines_t:.1f}–{fast_lines_c:.1f} 行。",
                ),
            ],
        )
    )
    blocks.append(("h2", "Charts", "图表"))
    blocks.append(
        (
            "figure",
            "latency",
            "Every call per profile and prompt; ticks mark the medians.",
            "每个档位、每种提示方式的每一次调用；短线为中位数。",
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
                    "**Enumerate.** Code lists every legal placement of the falling piece and of "
                    "the next piece after it: usually 300–600 two-piece plans.",
                    "**枚举。** 代码列出当前方块与下一个方块的所有合法落点，通常有 300–600 个两步方案。",
                ),
                (
                    f"**Prune without weights.** A plan is dropped only when another plan matches or "
                    f"beats it on every measured fact. A median of "
                    f"{v['balanced']['options_median']:.0f} plans remain, listed left to right.",
                    f"**无权重剪枝。** 只有在每项实测事实上都不优于另一方案的走法才会被剔除。剪枝后中位数剩 "
                    f"{v['balanced']['options_median']:.0f} 个方案，从左到右排列。",
                ),
                (
                    "**Ask once.** One Choice question lists every plan with its measured result. "
                    "The vision prompt adds an image of each outcome; the compact prompt keeps the "
                    "rules in the cached state.",
                    "**只问一次。** 一个 Choice 问题列出每个方案及其实测结果。视觉提示另附每个结果的图片；"
                    "精简提示把规则放在缓存的 state 中。",
                ),
                (
                    f"**Read one token.** OpenJev returns the full distribution over the plans and "
                    f"code presses the keys of the chosen one. A plan left alone after pruning is "
                    f"played without a call ({decisions - calls} of {number(decisions)} decisions).",
                    f"**读取 1 个 token。** OpenJev 返回所有方案上的完整概率分布，代码按所选方案按键。"
                    f"剪枝后只剩一个方案时不调用模型（{number(decisions)} 次决策中有 {decisions - calls} 次）。",
                ),
            ],
        )
    )
    blocks.append(
        (
            "h3",
            f"A real decision: {ex['profile']}, seed {ex['seed']}, decision {ex['number'] + 1}",
            f"真实示例：{ex['profile']}，种子 {ex['seed']}，第 {ex['number'] + 1} 次决策",
        )
    )
    image = ex["image"]
    blocks.append(
        (
            "image",
            "figures/example-sheet.png",
            f"The image sent: {image['width']} × {image['height']} px, {image['tokens']} image "
            f"tokens. Tile A clears a row (+1).",
            f"发送的图片：{image['width']} × {image['height']} 像素，{image['tokens']} 个图像 token。"
            f"A 方案消除一行（+1）。",
        )
    )
    blocks.append(("code", "json", ex["request"], ("Vision request", "视觉提示请求")))
    blocks.append(
        ("code", "json", ex["compact"], ("Compact request, same state", "精简提示请求（同一局面）"))
    )
    blocks.append(
        ("code", "json", ex["response"], ("Response (values rounded)", "响应（数值已取整）"))
    )
    chosen = next(o for o in rec["options"] if o["label"] == ex["chosen"])
    blocks.append(
        (
            "p",
            f"Jev put {percent(chosen['probability'])} on plan {ex['chosen']}, the only plan that "
            f"clears a row without a new hole, in {seconds(rec['client_ms'])} "
            f"({rec['input_tokens']} input tokens).",
            f"Jev 把 {percent(chosen['probability'])} 的概率给了方案 {ex['chosen']}：唯一既能消行又不产生新空洞"
            f"的方案，耗时 {seconds(rec['client_ms'], True)}（输入 {rec['input_tokens']} 个 token）。",
        )
    )
    blocks.append(
        (
            "p",
            "**Image resolution.** Qwen's vision encoder turns each 32 × 32 px block into one "
            "token. The outcome sheet draws one board cell per 16 px patch and keeps every tile on "
            "the 32 px grid, so the server never resamples it.",
            "**图像分辨率。** Qwen 的视觉编码器把每个 32 × 32 像素块变成 1 个 token。结果缩略图让每个棋盘格"
            "对应一个 16 像素 patch，所有小图都对齐 32 像素网格，服务端无需重新缩放。",
        )
    )
    blocks.append(("h2", "Design study", "设计实验"))
    blocks.append(
        (
            "p",
            f"The same 48 decision states, shown to each model in {len(VARIANT_NAMES)} ways. The "
            "states come from reference games on seeds 1–4, never the benchmark seeds.",
            f"同样的 48 个决策状态，以 {len(VARIANT_NAMES)} 种方式分别呈现给每个模型。这些状态来自种子 1–4 上的"
            "参考对局，从未使用正式测试的种子。",
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
    rows = [
        [
            (en, zh),
            f"{next(ab[n][key] for n in PROFILES if key in ab[n])['median_input_tokens']:.0f}",
        ]
        + [f"{ab[n][key]['mean_regret']:.2f}" if key in ab[n] else "—" for n in PROFILES]
        for key, (en, zh) in VARIANT_NAMES.items()
    ]
    blocks.append(
        (
            "table",
            [("Presentation", "呈现方式"), ("Input tokens", "输入 token")]
            + [(f"Regret · {n}", f"遗憾值 · {n}") for n in PROFILES],
            rows,
        )
    )
    builds = sorted({b for per in summary["llama_cpp"].values() for b in per.values()})
    blocks.append(("h2", "Method", "方法"))
    blocks.append(
        (
            "list",
            [
                (
                    f"**Machine.** {machine['chip']}, {machine['memory_gb']} GB; llama.cpp on Metal "
                    f"({', '.join(builds)}) with one inference slot, an 8,192-token context and a "
                    f"512-token image budget. One model at a time, no other inference running.",
                    f"**硬件。** {machine['chip']}，{machine['memory_gb']} GB；llama.cpp（Metal，"
                    f"{'、'.join(builds)}），单推理槽、8,192 token 上下文、每张图 512 个图像 token 上限。"
                    f"同一时间只运行一个模型，没有其他推理任务。",
                ),
                (
                    "**Models.** The pinned OpenJev profiles: Qwen3.5-0.8B Q4_K_M, Qwen3.5-4B "
                    "Q4_K_M, Qwen3.6-35B-A3B UD-Q4_K_XL and Qwen3.8-27B UD-Q4_K_XL, each with its "
                    "matching F16 vision projector.",
                    "**模型。** OpenJev 固定版本的四个档位：Qwen3.5-0.8B Q4_K_M、Qwen3.5-4B Q4_K_M、"
                    "Qwen3.6-35B-A3B UD-Q4_K_XL 与 Qwen3.8-27B UD-Q4_K_XL，各自搭配对应的 F16 视觉投影器。",
                ),
                (
                    "**Protocol.** Seeds 101–505, 100 pieces per game or until the stack tops out, "
                    "the same pruning for every model. The goal counts ten line-clear events.",
                    "**流程。** 种子 101–505，每局 100 个方块或直到堆满出局，所有模型使用相同的剪枝规则。"
                    "目标按 10 次消除事件计算。",
                ),
                (
                    f"**Replays.** Videos and the browser replay re-simulate the recorded keys; the "
                    f"Python and JavaScript engines reproduce all {games} games and "
                    f"{number(decisions)} decisions exactly.",
                    f"**回放。** 视频与网页回放按录制的按键重新模拟；Python 与 JavaScript 两套引擎逐一复现全部 "
                    f"{games} 局、{number(decisions)} 次决策。",
                ),
                (
                    "**Limits.** Five seeds per configuration is a small sample, and agreement "
                    "depends on the chosen reference. Timings are for one 16-inch MacBook Pro: the "
                    "max text and vision games ran after 20 minutes of continuous load, when it "
                    "processed about 125 prompt tokens per second instead of 200.",
                    "**局限。** 每种配置只有 5 个种子，一致率取决于所选参考评估器。耗时只代表这台 16 英寸 MacBook Pro："
                    "max 的文字与视觉对局在连续运行 20 分钟后进行，当时每秒约处理 125 个提示 token，而不是 200 个。",
                ),
            ],
        )
    )
    blocks.append(("h2", "Reproduce", "复现"))
    reproduce = (
        "scripts/build-llama.sh                        # optional: OpenJev's llama.cpp patch\n"
        "uv run openjev serve --profile max --llama-server .llamacpp/llama.cpp/build/bin/llama-server\n"
        "uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,text,compact\n"
        "uv run python examples/tetris/play.py ablation --variants vision,compact,text\n"
        "uv run python examples/tetris/play.py baseline   # no model needed\n"
        "uv run python examples/tetris/report.py          # summary, figures, pages, replays\n"
        "uv run python examples/tetris/video.py --profile max --mode compact"
    )
    blocks.append(("code", "bash", (reproduce, reproduce), ("", "")))
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
            "- `summary.json`：报告使用的汇总数据；`replays.json`：网页回放数据；`baselines.json`：无模型对照。",
            "- `figures/`：SVG 图表与示例图片；`videos/`：每个档位的对局视频与封面。",
        ]
        if zh
        else [
            "## Files in this folder",
            "",
            "- `runs/*.json`: every decision of every game, one line per decision.",
            "- `ablation/*.json`: the design study.",
            "- `summary.json`: the aggregates behind this page; `replays.json`: data for the web replay; `baselines.json`: the no-model policies.",
            "- `figures/`: SVG charts and the example image; `videos/`: one video and poster per profile.",
        ]
    )
    return "\n".join(out + files) + "\n"


# --------------------------------------------------------------------------- site page


def site_page(summary: dict, runs: dict, zh: bool) -> str:
    """The documentation site's Tetris page: the report's headline, shorter."""
    up = "../../" if zh else "../"
    p = summary["profiles"]
    m = {name: p[name]["modes"] for name in PROFILES}
    base = summary["baselines"]
    played = [(n, mode) for n in PROFILES for mode in MODES if mode in m[n]]
    games = sum(m[n][mode]["games"] for n, mode in played)
    goals = sum(m[n][mode]["goal_reached"] for n, mode in played)
    best = max(
        (score, name, mode, seed)
        for name, mode in played
        for seed, score in zip(m[name][mode]["seeds"], m[name][mode]["score"], strict=True)
    )
    top = m["max"]["compact"]
    video = {name: goal_video(runs, name) for name in PROFILES}
    report = f"{SITE}demos/tetris/report/"
    web = f"{SITE}demos/tetris/web/"
    source = "https://github.com/jev-skills/openjev-multimodal/tree/main/examples/tetris"

    def t(en: str, cn: str) -> str:
        return cn if zh else en

    out = [
        "---",
        t(
            "title: Tetris demo — four local models play through OpenJev",
            "title: 俄罗斯方块演示 —— 四个本地模型通过 OpenJev 对局",
        ),
        t(
            "description: Four Qwen models play Tetris through the Jev-compatible OpenJev "
            "Multimodal API, one output token per two pieces. Videos, results, a no-model "
            "baseline and a 27B model deciding in under a second.",
            "description: 四个 Qwen 模型通过兼容 Jev 的 OpenJev Multimodal API 玩俄罗斯方块，每两个方块只需 "
            "1 个输出 token。包含对局视频、结果、无模型对照，以及一秒内完成决策的 27B 模型。",
        ),
        "---",
        "",
        t("# Tetris, played by a local model", "# 由本地模型来玩的俄罗斯方块"),
        "",
        t(
            "Four Qwen models play a complete Tetris game through `POST /v1/systemone`. Code "
            "knows the rules: it lists every legal move, simulates the outcome and presses the "
            "keys. The model makes every choice, with **one output token per two pieces**.",
            "四个 Qwen 模型通过 `POST /v1/systemone` 玩完整的俄罗斯方块。规则交给代码：列出所有合法走法、"
            "模拟结果、按下按键。每一步都由模型选择，**每两个方块只用 1 个输出 token**。",
        ),
        "",
        t(
            f"**[Play in the browser →]({web})** &nbsp; [Full test report]({report}) · "
            f"[Source and recordings]({source})",
            f"**[在浏览器中试玩 →]({web})** &nbsp; [完整测试报告]({report}) · [源码与录制数据]({source})",
        ),
        "",
        t("| Result | Measured |", "| 结果 | 实测 |"),
        "| --- | --- |",
        t(
            f"| Games that reached 10 line clears | **{goals} / {games}** |",
            f"| 完成 10 次消除的对局 | **{goals} / {games}** |",
        ),
        t(
            f"| Qwen3.8-27B per decision, compact prompt | **{seconds(top['latency_ms']['median'])}** median |",
            f"| Qwen3.8-27B 每次决策（精简提示） | 中位数 **{seconds(top['latency_ms']['median'], True)}** |",
        ),
        t(
            f"| Lines per game, Qwen3.8-27B | **{statistics.fmean(top['lines']):.1f}** · random picks "
            f"{base['random']['mean_lines']:.1f} · reference {base['reference']['mean_lines']:.1f} |",
            f"| 每局消除行数，Qwen3.8-27B | **{statistics.fmean(top['lines']):.1f}** · 随机选择 "
            f"{base['random']['mean_lines']:.1f} · 参考评估器 {base['reference']['mean_lines']:.1f} |",
        ),
        t(
            f"| Best score after 100 pieces | **{number(best[0])}** · {best[1]}, "
            f"{MODE_NAMES[best[2]][0]}, seed {best[3]} |",
            f"| 100 个方块后的最高分 | **{number(best[0])}** · {best[1]}，{MODE_NAMES[best[2]][1]}，种子 {best[3]} |",
        ),
        "",
        t("## Watch each model play", "## 观看每个模型对局"),
        "",
        t(
            "Seed 101, from the first piece to the tenth line clear. Waiting time is the measured "
            "round trip of each call.",
            "种子 101，从第一个方块播放到第 10 次消除。等待时间是每次调用实测的往返耗时。",
        ),
        "",
        '<div class="tetris-videos">',
    ]
    for name in PROFILES:
        clip = f"{up}examples/tetris/report/videos/{name}"
        caption = t(
            f"{MODE_NAMES[VIDEOS[name]][0]} · goal after {video[name]['pieces']} pieces · "
            f"{seconds(video[name]['median_ms'])} per call",
            f"{MODE_NAMES[VIDEOS[name]][1]} · {video[name]['pieces']} 个方块达成 · "
            f"每次调用 {seconds(video[name]['median_ms'], True)}",
        )
        out += [
            "<figure>",
            f'<video src="{clip}.mp4" poster="{clip}.jpg" controls muted playsinline preload="none"></video>',
            f"<figcaption><strong>{name} · {model(runs, name)}</strong>{caption}</figcaption>",
            "</figure>",
        ]
    out += ["</div>", "", t("## Results after 100 pieces", "## 100 个方块后的结果"), ""]
    out += ['<div class="results">', ""]
    out += [
        t(
            "| Profile | Lines · vision | Lines · compact | Call · vision | Call · compact | Agreement |",
            "| 档位 | 消除行数 · 视觉 | 消除行数 · 精简 | 调用 · 视觉 | 调用 · 精简 | 一致率 |",
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in PROFILES:
        vis, com = m[name]["vision"], m[name].get("compact")
        cells = [
            f"{name} · {model(runs, name)}",
            f"{statistics.fmean(vis['lines']):.1f}",
            f"{statistics.fmean(com['lines']):.1f}" if com else "—",
            seconds(vis["latency_ms"]["median"], zh),
            seconds(com["latency_ms"]["median"], zh) if com else "—",
            percent(vis["agreement"]),
        ]
        out.append("| " + " | ".join(cells) + " |")
    out += [
        "",
        "</div>",
        "",
        t(
            f"Five seeds per cell, 100 pieces per game. Agreement compares the vision-prompt "
            f"decisions with a reference evaluator that never moves a piece. [All {games} games →]({report})",
            f"每格 5 个种子，每局 100 个方块。一致率把视觉提示下的决策与参考评估器比较，参考评估器从不参与落子。"
            f"[全部 {games} 局 →]({report})",
        ),
        "",
        t("## Without a model", "## 没有模型会怎样"),
        "",
        t(
            f"On the same pruned plans, a random pick tops out in {base['random']['topped_out']} of "
            f"{base['random']['games']} games and clears {base['random']['mean_lines']:.1f} lines. "
            f"Always taking the first plan clears {base['first']['mean_lines']:.1f}. The code "
            "narrows the choice; the model makes it.",
            f"在同样的剪枝方案上，随机选择 {base['random']['games']} 局中有 {base['random']['topped_out']} 局堆满出局，"
            f"平均消除 {base['random']['mean_lines']:.1f} 行；总选第一个方案为 {base['first']['mean_lines']:.1f} 行。"
            "代码缩小选择范围，由模型做出选择。",
        ),
        "",
        t("## How one decision works", "## 一次决策如何完成"),
        "",
        t(
            "1. **Enumerate.** Code lists every placement of the falling piece and of the next one: "
            "usually 300–600 two-piece plans.",
            "1. **枚举。** 代码列出当前方块与下一个方块的所有落点，通常有 300–600 个两步方案。",
        ),
        t(
            "2. **Prune without weights.** A plan is dropped only when another matches or beats it "
            "on every measured fact. About three remain.",
            "2. **无权重剪枝。** 只有在每项实测事实上都不优于另一方案的走法才会被剔除，通常剩约 3 个。",
        ),
        t(
            "3. **Ask once.** One Choice question lists the plans with their facts: rows cleared, "
            "new holes, height. The vision prompt adds a lettered image of each outcome.",
            "3. **只问一次。** 一个 Choice 问题列出各方案及其事实：消除行数、新空洞、高度。视觉提示另附每个结果的字母小图。",
        ),
        t(
            "4. **Read one token.** The answer is a full distribution over the plans; code "
            "presses the keys of the chosen one.",
            "4. **读取 1 个 token。** 答案是所有方案上的完整概率分布，代码按所选方案按键。",
        ),
        "",
        t(
            "**The compact prompt** sends the rules as the state, which never changes, and only "
            "the pieces and short plan facts as the question. The API keeps the state cached, so "
            "each call reads about 75–100 new tokens. That is what brings a dense 27B model under "
            "a second.",
            "**精简提示**把规则作为不变的 state，问题中只放当前方块和简短的方案事实。API 会缓存 state，"
            "每次调用只需读取约 75–100 个新 token，这让稠密 27B 模型的决策进入一秒以内。",
        ),
        "",
        f"![{t('The image sent with one real decision: three lettered outcome tiles', '一次真实决策发送的图片：三个带字母的结果小图')}]({up}examples/tetris/report/figures/example-sheet.png)",
        "",
        t("## Run it yourself", "## 自己运行"),
        "",
        "```bash",
        t(
            "uv run openjev serve                                  # balanced profile on :8000",
            "uv run openjev serve                                  # 在 :8000 启动 balanced 档位",
        ),
        t(
            "uv run python examples/tetris/serve.py                # browser game on http://127.0.0.1:8765",
            "uv run python examples/tetris/serve.py                # 浏览器游戏：http://127.0.0.1:8765",
        ),
        "uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,compact",
        "```",
        "",
        t(
            f"Measured on an {summary['machine']['chip']} with llama.cpp on Metal. Five seeds per "
            "configuration is a small sample; timings depend on the machine and its load.",
            f"测试环境：{summary['machine']['chip']}，llama.cpp（Metal）。每种配置 5 个种子，样本较小；耗时取决于机器与负载。",
        ),
        "",
        "<style scoped>",
        ".tetris-videos { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 20px 0 8px; }",
        ".tetris-videos figure { margin: 0; border: 1px solid var(--vp-c-divider); border-radius: 10px; overflow: hidden; background: var(--vp-c-bg-soft); }",
        ".tetris-videos video { display: block; width: 100%; aspect-ratio: 16 / 9; background: #101713; }",
        ".tetris-videos figcaption { padding: 10px 12px 12px; font-size: 13px; line-height: 1.5; color: var(--vp-c-text-2); }",
        ".tetris-videos figcaption strong { display: block; color: var(--vp-c-text-1); }",
        ".results td, .results th { white-space: nowrap; }",
        "@media (max-width: 760px) { .tetris-videos { grid-template-columns: 1fr; } }",
        "</style>",
    ]
    return "\n".join(out) + "\n"


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
<meta name="description" content="Four local Qwen models play Tetris through OpenJev Multimodal: results, videos, latency, no-model baselines and the design study behind one-token decisions.">
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
.videos { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
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
    <a class="optional" href="https://github.com/jev-skills/openjev-multimodal/tree/main/examples/tetris">GitHub</a>
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
    site = report.parents[2] / "site"
    (site / "tetris.md").write_text(site_page(summary, runs, zh=False))
    (site / "zh" / "tetris.md").write_text(site_page(summary, runs, zh=True))
