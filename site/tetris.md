---
title: Tetris demo — a local model plays through OpenJev
description: Three Qwen models play Tetris through the Jev-compatible OpenJev Multimodal API with one output token per two pieces. Videos, latency, results and a design study of image resolution.
---

# Tetris, played by a local model

A complete Tetris game that Qwen models play through `POST /v1/systemone`. Code knows the rules: it lists every legal move, measures the result and presses the keys. OpenJev supplies the judgment: it reads a short list of plans, looks at a lettered picture of their outcomes and picks one with **a single output token for every two pieces**.

**[Play in the browser →](https://hand-in.github.io/openjev-multimodal/demos/tetris/web/)** &nbsp; [Full test report](https://hand-in.github.io/openjev-multimodal/demos/tetris/report/) · [Source and recordings](https://github.com/Hand-In/openjev-multimodal/tree/main/examples/tetris)

| Result | Measured |
| --- | --- |
| Games that reached 10 line clears (vision prompt) | **15 / 15**, with no illegal key, API error or fallback move |
| Quality games that reached the goal with no hole | **3 / 5** (4 / 5 with the text-only prompt) |
| Median time per decision (fast · balanced · quality) | **0.15 · 0.65 · 0.91 s** |
| Best score after 100 pieces | **15,156** (quality, text-only prompt, seed 101) |

## Watch each model play

Seed 101, vision prompt, from the first piece to the tenth line clear. Waiting time is the measured round trip of each call; key presses, drops and clears are animated at a fixed pace.

<div class="tetris-videos">
<figure>
<video src="../examples/tetris/report/videos/fast.mp4" poster="../examples/tetris/report/videos/fast.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>fast · Qwen3.5-0.8B</strong>goal after 56 pieces · 20 holes · 0.14 s per call</figcaption>
</figure>
<figure>
<video src="../examples/tetris/report/videos/balanced.mp4" poster="../examples/tetris/report/videos/balanced.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>balanced · Qwen3.5-4B</strong>goal after 30 pieces · 2 holes · 0.51 s per call</figcaption>
</figure>
<figure>
<video src="../examples/tetris/report/videos/quality.mp4" poster="../examples/tetris/report/videos/quality.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>quality · Qwen3.6-35B-A3B</strong>goal after 32 pieces · 1 hole · 0.92 s per call</figcaption>
</figure>
</div>

## How one decision works

1. **Enumerate.** Code lists every placement of the falling piece (rotate, shift, hard drop) and every placement of the next piece after it: usually 300–600 two-piece plans.
2. **Prune without weights.** A plan is dropped only when another plan matches or beats it on every measured fact: rows cleared, holes, stack height, aggregate height and bumpiness. A median of three plans remain, listed left to right, so their order carries no hint.
3. **Ask once.** One Choice question lists each plan as a complete key sequence with its measured result. One image shows each plan's outcome as a lettered tile.
4. **Read one token.** The answer is the full distribution over the plan labels; code presses the chosen keys for both pieces. When only one plan survives pruning, it is played without a call.

```text
J: left left left drop → cols 0-2; then S: drop → cols 3-5. Result: clears 1, new holes 0, height 1
```

![The image sent with one real decision: three lettered outcome tiles, tile A clears a row](../examples/tetris/report/figures/example-sheet.png)

In this real decision the quality model put 81% on plan A, the only plan that clears a row without a new hole. The call took 0.93 s with 490 input tokens.

**Image resolution.** Qwen's vision encoder cuts images into 16 px patches and merges each 2 × 2 group into one token (32 px). The outcome sheet draws one board cell per 16 px patch, crops each tile to the rows in use and keeps every tile on the 32 px grid, so a three-plan sheet is 576 × 128 px, costs 72 image tokens and is never resampled by the server.

## Results after 100 pieces

Five seeds per row (101, 202, 303, 404, 505); every model sees the same piece sequences.

| Profile | Prompt | 10 clears | Hole-free goal | Topped out | Lines (mean) | Score (mean / best) | Call median · p90 | Agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fast · 0.8B | vision | 5 / 5 | 0 / 5 | 1 / 5 | 26.6 | 7,186 / 8,714 | 0.15 · 0.18 s | 42% |
| fast · 0.8B | text only | 4 / 5 | 0 / 5 | 5 / 5 | 13.6 | 3,199 / 5,410 | 0.08 · 0.10 s | 28% |
| balanced · 4B | vision | 5 / 5 | 0 / 5 | 0 / 5 | 35.8 | 11,837 / 13,668 | 0.65 · 0.89 s | 73% |
| balanced · 4B | text only | 5 / 5 | 1 / 5 | 0 / 5 | 36.4 | 12,818 / 13,868 | 0.51 · 0.64 s | 72% |
| quality · 35B-A3B | vision | 5 / 5 | 3 / 5 | 0 / 5 | 38.2 | 13,696 / 14,416 | 0.91 · 1.13 s | 84% |
| quality · 35B-A3B | text only | 5 / 5 | 4 / 5 | 0 / 5 | 38.2 | 14,384 / 15,156 | 0.55 · 0.64 s | 82% |

Agreement compares each non-forced decision with a reference evaluator (Yiyuan Lee's tuned weights) that never influences a move.

![Round-trip latency of every call per profile, with medians](../examples/tetris/report/figures/latency.svg)

![Score, lines cleared and most holes after 100 pieces, one dot per game](../examples/tetris/report/figures/outcomes.svg)

## What the runs show

- **Every model reached the goal.** All vision-mode games cleared 10 lines. The quality model did it with a hole-free stack in 3 of 5 games.
- **A larger model buys better judgment.** Agreement with the reference rises from 42% (0.8B) to 73% (4B) and 84% (35B-A3B). The 35B mixture-of-experts model activates about 3B parameters per token, so it decides in 0.91 s, only 1.4× the 4B model.
- **Exact facts decide; the image explains.** Given only the outcome images, every model chooses poorly. Facts plus the outcome sheet give every model its lowest regret in the design study below.
- **The picture matters most to the smallest model.** The 0.8B model cleared 26.6 lines on average with the outcome sheet and 13.6 without it. For the 4B and 35B models, the text-only prompt played about as well and saved 142–360 ms per call.
- **Choose the picture first, then the fewest tokens that stay legible.** Doubling the sheet adds about 150 input tokens without better decisions. A full-board screenshot made the 4B model both slower and worse.

![Design study: mean regret and median call time for eight presentations of the same 48 decision states](../examples/tetris/report/figures/design.svg)

## Run it yourself

```bash
uv run openjev serve                                  # balanced profile on :8000
uv run python examples/tetris/serve.py                # browser game on http://127.0.0.1:8765
uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505
```

The browser game replays every recorded run key by key, lets your local model play live, or lets you play. Replays re-simulate the recorded keys with the same engine used for the benchmark, in Python and in JavaScript. Measured on an Apple M3 Max with llama.cpp b9670; five seeds per configuration is a small sample, and timings depend on the machine and load.

<style scoped>
.tetris-videos { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 20px 0 8px; }
.tetris-videos figure { margin: 0; border: 1px solid var(--vp-c-divider); border-radius: 10px; overflow: hidden; background: var(--vp-c-bg-soft); }
.tetris-videos video { display: block; width: 100%; aspect-ratio: 16 / 9; background: #101713; }
.tetris-videos figcaption { padding: 10px 12px 12px; font-size: 13px; line-height: 1.5; color: var(--vp-c-text-2); }
.tetris-videos figcaption strong { display: block; color: var(--vp-c-text-1); }
@media (max-width: 760px) { .tetris-videos { grid-template-columns: 1fr; } }
</style>
