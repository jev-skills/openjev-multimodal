---
title: Tetris demo — four local models play through OpenJev
description: Four Qwen models play Tetris through the Jev-compatible OpenJev Multimodal API, one output token per two pieces. Videos, results, a no-model baseline and a 27B model deciding in under a second.
---

# Tetris, played by a local model

Four Qwen models play a complete Tetris game through `POST /v1/systemone`. Code knows the rules: it lists every legal move, simulates the outcome and presses the keys. The model makes every choice, with **one output token per two pieces**.

**[Play in the browser →](https://jev-skills.github.io/openjev-multimodal/demos/tetris/web/)** &nbsp; [Full test report](https://jev-skills.github.io/openjev-multimodal/demos/tetris/report/) · [Source and recordings](https://github.com/jev-skills/openjev-multimodal/tree/main/examples/tetris)

| Result | Measured |
| --- | --- |
| Games that reached 10 line clears | **58 / 60** |
| Qwen3.8-27B per decision, compact prompt | **0.73 s** median |
| Lines per game, Qwen3.8-27B | **38.2** · random picks 14.3 · reference 37.8 |
| Best score after 100 pieces | **15,262** · quality, compact, seed 202 |

## Watch each model play

Seed 101, from the first piece to the tenth line clear. Waiting time is the measured round trip of each call.

<div class="tetris-videos">
<figure>
<video src="../examples/tetris/report/videos/fast.mp4" poster="../examples/tetris/report/videos/fast.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>fast · Qwen3.5-0.8B</strong>vision · goal after 56 pieces · 0.14 s per call</figcaption>
</figure>
<figure>
<video src="../examples/tetris/report/videos/balanced.mp4" poster="../examples/tetris/report/videos/balanced.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>balanced · Qwen3.5-4B</strong>vision · goal after 30 pieces · 0.51 s per call</figcaption>
</figure>
<figure>
<video src="../examples/tetris/report/videos/quality.mp4" poster="../examples/tetris/report/videos/quality.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>quality · Qwen3.6-35B-A3B</strong>vision · goal after 32 pieces · 0.92 s per call</figcaption>
</figure>
<figure>
<video src="../examples/tetris/report/videos/max.mp4" poster="../examples/tetris/report/videos/max.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>max · Qwen3.8-27B</strong>compact · goal after 32 pieces · 0.66 s per call</figcaption>
</figure>
</div>

## Results after 100 pieces

<div class="results">

| Profile | Lines · vision | Lines · compact | Call · vision | Call · compact | Agreement |
| --- | ---: | ---: | ---: | ---: | ---: |
| fast · Qwen3.5-0.8B | 26.6 | 17.4 | 0.15 s | 0.03 s | 42% |
| balanced · Qwen3.5-4B | 35.8 | 33.0 | 0.65 s | 0.12 s | 73% |
| quality · Qwen3.6-35B-A3B | 38.2 | 38.2 | 0.91 s | 0.14 s | 84% |
| max · Qwen3.8-27B | 38.4 | 38.2 | 4.08 s | 0.73 s | 85% |

</div>

Five seeds per cell, 100 pieces per game. Agreement compares the vision-prompt decisions with a reference evaluator that never moves a piece. [All 60 games →](https://jev-skills.github.io/openjev-multimodal/demos/tetris/report/)

## Without a model

On the same pruned plans, a random pick tops out in 90 of 100 games and clears 14.3 lines. Always taking the first plan clears 16.0. The code narrows the choice; the model makes it.

## How one decision works

1. **Enumerate.** Code lists every placement of the falling piece and of the next one: usually 300–600 two-piece plans.
2. **Prune without weights.** A plan is dropped only when another matches or beats it on every measured fact. About three remain.
3. **Ask once.** One Choice question lists the plans with their facts: rows cleared, new holes, height. The vision prompt adds a lettered image of each outcome.
4. **Read one token.** The answer is a full distribution over the plans; code presses the keys of the chosen one.

**The compact prompt** sends the rules as the state, which never changes, and only the pieces and short plan facts as the question. The API keeps the state cached, so each call reads about 75–100 new tokens. That is what brings a dense 27B model under a second.

![The image sent with one real decision: three lettered outcome tiles](../examples/tetris/report/figures/example-sheet.png)

## Run it yourself

```bash
uv run openjev serve                                  # balanced profile on :8000
uv run python examples/tetris/serve.py                # browser game on http://127.0.0.1:8765
uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,compact
```

Measured on an Apple M3 Max with llama.cpp on Metal. Five seeds per configuration is a small sample; timings depend on the machine and its load.

<style scoped>
.tetris-videos { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 20px 0 8px; }
.tetris-videos figure { margin: 0; border: 1px solid var(--vp-c-divider); border-radius: 10px; overflow: hidden; background: var(--vp-c-bg-soft); }
.tetris-videos video { display: block; width: 100%; aspect-ratio: 16 / 9; background: #101713; }
.tetris-videos figcaption { padding: 10px 12px 12px; font-size: 13px; line-height: 1.5; color: var(--vp-c-text-2); }
.tetris-videos figcaption strong { display: block; color: var(--vp-c-text-1); }
.results td, .results th { white-space: nowrap; }
@media (max-width: 760px) { .tetris-videos { grid-template-columns: 1fr; } }
</style>
