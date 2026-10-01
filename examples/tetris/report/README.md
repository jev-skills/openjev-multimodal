# Tetris test report

[Visual report](https://hand-in.github.io/openjev-multimodal/demos/tetris/report/) · [Play in the browser](https://hand-in.github.io/openjev-multimodal/demos/tetris/web/) · [How the example works](../README.md) · [中文](README.zh-CN.md)

Three local models each played ten games of 100 pieces through OpenJev Multimodal: five seeds, two prompt styles, the same piece sequences for every model. Every call asks one Choice question about the next two pieces and reads a single output token. The tables, charts, videos and the browser replay are all generated from the recordings (measured 2026-09-21 on an Apple M3 Max).

- **15 / 15** vision games reached 10 line clears (0 illegal keys · 0 API errors · 0 fallback moves)
- **3 / 5** quality games reached the goal with no hole (4 / 5 with the text-only prompt)
- **0.15 · 0.65 · 0.91 s** median time per decision (fast · balanced · quality; one call plans two pieces)
- **15,156** best score after 100 pieces (quality · text-only · seed 101)

## Watch each model play

Seed 101 with the vision prompt, from the first piece to the tenth line clear. Waiting time is the measured round trip of each call; key presses, drops and clears are animated at a fixed pace.

| [![fast · Qwen3.5-0.8B](videos/fast.jpg)](videos/fast.mp4)<br>**fast · Qwen3.5-0.8B**<br>goal after 56 pieces · 20 holes · 0.14 s per call | [![balanced · Qwen3.5-4B](videos/balanced.jpg)](videos/balanced.mp4)<br>**balanced · Qwen3.5-4B**<br>goal after 30 pieces · 2 holes · 0.51 s per call | [![quality · Qwen3.6-35B-A3B](videos/quality.jpg)](videos/quality.mp4)<br>**quality · Qwen3.6-35B-A3B**<br>goal after 32 pieces · 1 hole · 0.92 s per call |
|---|---|---|

## What the runs show

- **Every model reached the goal.** All 15 vision-mode games cleared 10 lines with no illegal key, no API error and no fallback move. The quality model reached the goal with a hole-free stack in 3 of its 5 games (4 of 5 with the text-only prompt).
- **A larger model buys better judgment.** Agreement with the reference evaluator rises from 42% (0.8B) to 73% (4B) and 84% (35B-A3B); mean regret falls from 1.87 to 0.69 and 0.09. The 35B mixture-of-experts model activates about 3B parameters per token, so it decides in 0.91 s, only 1.4× the 4B model.
- **Exact facts decide; the image explains.** Shown only the outcome images, every model loses 2.4–2.6 points of value per decision on the fixed states. Facts alone bring the 4B and 35B models down to 0.27, and facts plus the outcome sheet give every model its lowest regret: 1.44, 0.22, 0.18.
- **The picture matters most to the smallest model.** In full games the 0.8B model cleared 26.6 lines on average with the outcome sheet and 13.6 without it, and topped out in 1 game instead of 5. For the 4B and 35B models the text-only prompt played about as well and saved 142–360 ms per call.
- **Choose the picture first, then the fewest tokens that stay legible.** Doubling the outcome sheet adds about 150 input tokens without better decisions, and halving it changes little. A full-board screenshot is the wrong picture for this decision: for the 4B model it raised regret from 0.22 to 0.67 and the median call from 0.59 s to 0.94 s.
- **Latency follows input tokens.** Every call returns one output token. Server time matches the round trip within about 1 ms and planning in code takes 25–35 ms, so prompt length, image tokens and model size set the pace.

## Results after 100 pieces

| Profile | Prompt | 10 clears | Hole-free goal | Topped out | Pieces to goal | Lines | Score (mean / best) | Most holes | Call median · p90 | Agreement | Regret |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fast · Qwen3.5-0.8B | vision | 5 / 5 | 0 / 5 | 1 / 5 | 48 | 26.6 | 7,186 / 8,714 | 29 | 0.15 s · 0.18 s | 42% | 1.87 |
| fast · Qwen3.5-0.8B | text only | 4 / 5 | 0 / 5 | 5 / 5 | 54 | 13.6 | 3,199 / 5,410 | 28 | 0.08 s · 0.10 s | 28% | 2.35 |
| balanced · Qwen3.5-4B | vision | 5 / 5 | 0 / 5 | 0 / 5 | 40 | 35.8 | 11,837 / 13,668 | 9 | 0.65 s · 0.89 s | 73% | 0.69 |
| balanced · Qwen3.5-4B | text only | 5 / 5 | 1 / 5 | 0 / 5 | 30 | 36.4 | 12,818 / 13,868 | 5 | 0.51 s · 0.64 s | 72% | 0.67 |
| quality · Qwen3.6-35B-A3B | vision | 5 / 5 | 3 / 5 | 0 / 5 | 28 | 38.2 | 13,696 / 14,416 | 3 | 0.91 s · 1.13 s | 84% | 0.09 |
| quality · Qwen3.6-35B-A3B | text only | 5 / 5 | 4 / 5 | 0 / 5 | 34 | 38.2 | 14,384 / 15,156 | 3 | 0.55 s · 0.64 s | 82% | 0.25 |

Five games per row (seeds 101, 202, 303, 404, 505). Pieces to goal and most holes are medians over the games; lines are means. Agreement and regret compare each non-forced decision with the reference evaluator (Yiyuan Lee's tuned weights), which never influences a move.

## Charts

![Every vision-mode call per profile. The white tick marks the median, the gray tick the text-only median.](figures/latency.svg)

*Every vision-mode call per profile. The white tick marks the median, the gray tick the text-only median.*

![Score, lines cleared and most holes after 100 pieces; one dot per game.](figures/outcomes.svg)

*Score, lines cleared and most holes after 100 pieces; one dot per game.*

## How one decision works

1. **Enumerate.** Code lists every legal placement of the falling piece (rotate, shift, hard drop) and every placement of the next piece after it: usually 300–600 two-piece plans.
2. **Prune without weights.** A plan is dropped only when another plan matches or beats it on every measured fact: rows cleared, holes, stack height, aggregate height and bumpiness. A median of 3 plans remain; they are listed left to right, so their order carries no hint.
3. **Ask once.** One Choice question lists each plan as a complete key sequence with its measured result, and one image shows the outcome of every plan as a lettered tile.
4. **Read one token.** OpenJev returns the full distribution over the option labels and code presses the chosen keys for both pieces. When pruning leaves a single plan, it is played without a call and counted as forced (103 of 1,427 decisions).

### A real decision: the quality run, seed 101, decision 8

![The image sent: 576 × 128 px, 72 image tokens. Tile A clears a row (+1).](figures/example-sheet.png)

*The image sent: 576 × 128 px, 72 image tokens. Tile A clears a row (+1).*

**Request**

```json
{
  "model": "jev-latest",
  "state": {
    "game": "Tetris well: 10 columns (0-9, left to right) x 20 rows",
    "falling": "J",
    "next": [
      "S",
      "O",
      "I"
    ],
    "lines_cleared": 5
  },
  "questions": {
    "plan": {
      "type": "choice",
      "instructions": {
        "task": "Choose the plan to play: the keys for the falling piece, then for the next piece.",
        "goal": "Clear lines and keep the well healthy for the pieces that follow.",
        "priorities": [
          "Complete rows whenever possible; more rows at once is better.",
          "Do not cover empty cells: new holes are the most expensive mistake.",
          "Keep the stack low and its surface even, so the next pieces fit."
        ],
        "fields": {
          "cols": "columns the piece occupies after the drop",
          "clears": "rows completed by the two moves",
          "new holes": "empty cells the two moves seal under blocks",
          "height": "tallest column afterwards, in rows"
        },
        "image": "The image has one tile per option, lettered like the options: the well after both pieces land. +N marks rows cleared; dark gaps under blocks are holes."
      },
      "criteria": {
        "0": "J: left left left drop → cols 0-2; then S: drop → cols 3-5. Result: clears 1, new holes 0, height 1",
        "1": "J: left drop → cols 2-4; then S: rotate-back left left left drop → cols 0-1. Result: clears 0, new holes 1, height 3",
        "2": "J: rotate rotate right right right right drop → cols 7-9; then S: right drop → cols 4-6. Result: clears 0, new holes 3, height 3"
      }
    }
  },
  "images": [
    "data:image/png;base64,iVBORw0KGgoAAAANSU… (2 KB PNG)"
  ]
}
```

**Response (values rounded)**

```json
{
  "model": "jev-latest",
  "answers": {
    "plan": {
      "type": "choice",
      "choice": "0",
      "probabilities": {
        "0": 0.8122,
        "1": 0.099,
        "2": 0.0887
      },
      "confidence": 0.4421
    }
  },
  "usage": {
    "input_tokens": 490,
    "output_tokens": 1
  }
}
```

Jev put 81% on plan A, the only plan that clears a row without a new hole. The call took 0.93 s with 490 input tokens.

**Image resolution.** Qwen's vision encoder cuts images into 16 px patches and merges each 2 × 2 group into one token (32 px). The outcome sheet draws one board cell per 16 px patch, crops each tile to the rows in use and keeps every tile on the 32 px grid, so the server never resamples it (it stays under 1,024 px and 512 image tokens).

## Design study

Before the benchmark, the same 48 decision states were shown to each model in eight ways. The states come from reference games on seeds 1–4; the benchmark seeds were never used while designing the prompt.

![Mean regret per presentation (lower is better) and the median call time.](figures/design.svg)

*Mean regret per presentation (lower is better) and the median call time.*

| Presentation | Input tokens | Regret · fast | Regret · balanced | Regret · quality | Call · fast | Call · balanced | Call · quality |
|---|---|---|---|---|---|---|---|
| Facts + outcome sheet (default) | 492 | 1.44 | 0.22 | 0.18 | 137 ms | 593 ms | 938 ms |
| Facts + sheet at ½ size | 438 | 1.18 | 0.30 | 0.06 | 111 ms | 439 ms | 587 ms |
| Facts + sheet at 2× | 642 | 1.38 | 0.35 | 0.17 | 162 ms | 647 ms | 864 ms |
| Facts only, no image | 374 | 1.58 | 0.27 | 0.27 | 90 ms | 428 ms | 566 ms |
| Facts + board screenshot | 696 | 2.39 | 0.67 | 0.24 | 199 ms | 936 ms | 1278 ms |
| Facts + screenshot at ½ size | 480 | 1.69 | 0.52 | 0.22 | 128 ms | 675 ms | 907 ms |
| Facts + screenshot at 2× | 888 | 1.77 | 0.68 | 0.27 | 272 ms | 1414 ms | 1645 ms |
| Outcome sheet only, no facts | 410 | 2.43 | 2.40 | 2.60 | 123 ms | 520 ms | 817 ms |

## Method and provenance

- **Machine.** Apple M3 Max, 128 GB; llama.cpp b9670 on Metal with one inference slot, four CPU threads, an 8,192-token context and a 512-token image budget. Profiles ran one after another, with one profile active at a time and no other inference running.
- **Models.** The pinned OpenJev profiles: Qwen3.5-0.8B Q4_K_M, Qwen3.5-4B Q4_K_M and Qwen3.6-35B-A3B UD-Q4_K_XL, each with its matching F16 vision projector. Weight files were checked by SHA-256 against the pinned Hugging Face revisions.
- **Protocol.** Seeds 101, 202, 303, 404 and 505; 100 pieces per game or until the stack tops out; the same seeds, prompt and pruning for every model. The goal counts ten separate line-clear events.
- **Measured.** Client round trip (localhost), server time (`x-openjev-elapsed-ms`), input tokens, the full probability distribution and every key pressed. The reference evaluator only scores decisions after the fact.
- **Replays.** Videos and the browser replay re-simulate the recorded keys. The Python and JavaScript engines reproduce all 30 games, 1,427 decisions and every option exactly.
- **Limits.** Five seeds per configuration is a small sample; regret and agreement depend on the chosen reference evaluator; timings are for one Mac without concurrent load. Pieces spawn inside the visible well; there is no hold piece and no soft-drop tucks or spins.

## Reproduce

```bash
uv run openjev serve --profile balanced     # one profile at a time
uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,text
uv run python examples/tetris/play.py ablation
uv run python examples/tetris/report.py     # summary, figures, pages, replays
uv run python examples/tetris/video.py --profile balanced --seed 101
```

## Files in this folder

- `runs/*.json`: every decision of every game, one line per decision.
- `ablation/*.json`: the design study.
- `summary.json`: the aggregates behind this page; `replays.json`: data for the web replay.
- `figures/`: SVG charts and the example image; `videos/`: one video and poster per profile.
