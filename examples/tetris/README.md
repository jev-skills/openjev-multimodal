# Tetris, played by OpenJev Multimodal

**A complete Tetris game that a local model plays through the SystemOne API.** Code knows the rules: it lists every legal move, simulates the result and presses the keys. The model supplies the judgment: it reads a short list of plans and picks one with a single output token.

[![Qwen3.8-27B plays Tetris through OpenJev Multimodal](report/videos/max.jpg)](report/videos/max.mp4)

[Test report](report/README.md) · [Visual report](https://hand-in.github.io/openjev-multimodal/demos/tetris/report/) · [Play in the browser](https://hand-in.github.io/openjev-multimodal/demos/tetris/web/) · [中文](README.zh-CN.md)

## Run it

```bash
uv run openjev serve                                  # balanced profile on :8000
uv run python examples/tetris/play.py play --seed 7   # one game, move by move, in the terminal
uv run python examples/tetris/serve.py                # browser game on http://127.0.0.1:8765
```

The browser game has three modes. **Replay** re-plays the recorded runs key by key with their real probabilities and timings; it also works as a static page. **Live Jev** asks your local model for every move. **Play** is ordinary Tetris for people: `←` `→` move, `↑` or `X` rotate, `Z` rotate back, `↓` soft drop, `Space` hard drop, `P` pause.

## How a decision works

One call decides the **falling piece and the next piece**, so a game of 100 pieces needs at most 50 calls.

1. **Enumerate.** `tetris.py` lists every placement reachable by rotating, shifting and hard dropping, then every placement of the next piece: usually 300–600 plans.
2. **Prune without weights.** A plan survives only if no other plan matches or beats it on all five measured facts (rows cleared, holes, stack height, aggregate height, bumpiness). A median of three plans remain, listed left to right so that position carries no hint. If one plan remains, it is played without a call.
3. **Ask once.** Each plan becomes one Choice option: the complete key sequence for both pieces plus its measured result.

   ```text
   J: left left left drop → cols 0-2; then S: drop → cols 3-5. Result: clears 1, new holes 0, height 1
   ```

   The instructions state the goal, the priorities (clear rows, never seal empty cells, keep the stack low and even) and define every field. Game state is sent as JSON: falling piece, next three pieces, lines cleared.
4. **Show the outcomes.** In the default `vision` prompt, one image draws the well after each plan as a lettered tile, with `+N` for cleared rows. Holes are visible as dark gaps.
5. **Read one token.** The answer is the full probability distribution over the plan labels. `play.py` presses the chosen keys and checks that every key had an effect; there is no fallback move.

### Image resolution

Qwen's vision encoder cuts images into 16 px patches and merges each 2 × 2 group into one token (32 px). The outcome sheet draws one board cell per 16 px patch, crops each tile to the rows in use and keeps every tile on the 32 px grid, so a three-plan sheet is 576 × 128 px and costs 72 image tokens. The server never resamples it.

### Three prompts

- `vision` (default): facts plus the outcome sheet. The small models need the picture.
- `text`: the same facts without an image.
- `compact`: the rules become the state, which never changes, and the question holds only the pieces and one short line per plan. The API keeps the state cached, so each call reads 75–100 new tokens. Large models play as well this way, several times faster.

The [design study](report/README.md#design-study) compares nine presentations on the same 48 states. Exact facts carry the decision: the image alone is not enough for any model, and a full-board screenshot is slower and worse than the outcome sheet.

## Results

Five seeds × 100 pieces per profile and prompt. Full numbers, charts and videos are in the [test report](report/README.md).

| Profile | Model | Lines · vision | Lines · compact | Call · vision | Call · compact |
| --- | --- | ---: | ---: | ---: | ---: |
| `fast` | Qwen3.5-0.8B | 26.6 | 17.4 | 0.15 s | 0.03 s |
| `balanced` | Qwen3.5-4B | 35.8 | 33.0 | 0.65 s | 0.12 s |
| `quality` | Qwen3.6-35B-A3B | 38.2 | 38.2 | 0.91 s | 0.14 s |
| `max` | Qwen3.8-27B | 38.4 | 38.2 | 4.08 s | 0.73 s |

Without a model, random picks among the same plans clear 14.3 lines per game (`play.py baseline`).

## Reproduce the benchmark

Run one profile at a time, then rebuild the report from the recordings. No inference happens after the first two commands.

```bash
uv run openjev serve --profile balanced
uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,text,compact
uv run python examples/tetris/play.py ablation --variants vision,compact,text
uv run python examples/tetris/play.py baseline        # no model needed
uv run python examples/tetris/report.py
uv run python examples/tetris/video.py --profile balanced --seed 101   # needs ffmpeg
```

`bench` writes `report/runs/<profile>.json` with every decision; `report.py` regenerates the summary, charts, pages and replay data.

## Files

| File | Purpose |
| --- | --- |
| `tetris.py` | Engine: SRS rotation, seeded 7-bag, placements, two-piece plans, dominance frontier |
| `vision.py` | Images for Jev: the outcome sheet and the full-board view used in the design study |
| `jev.py` | The prompt, the request and a minimal OpenJev client |
| `play.py` | `play`, `bench`, `ablation`, `baseline` and `probe` commands |
| `replay.py` | Re-simulates a recorded game and checks it against the recording |
| `video.py` | Renders replay videos (H.264, 1280 × 720) |
| `report.py`, `pages.py` | Summary, charts and the report pages |
| `serve.py`, `web/` | Browser game with replay, live Jev and human play; `web/tetris.js` mirrors `tetris.py` exactly |
| `report/` | Recorded runs, design study, charts, videos and the test report |
