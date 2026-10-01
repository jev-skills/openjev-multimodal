# Delivery receipt

Published and verified on September 21, 2026. Commit author and committer dates are fixed at October 1, 2026, as for the rest of the history; they are not the measurement dates.

- Profile: `uv run openjev serve --profile max` runs Qwen3.8-27B UD-Q4_K_XL (`unsloth/Qwen3.8-27B-GGUF` at `4ca72078`) with its F16 projector.
- Inference: the API caches a repeated state (`OPENJEV_PRIME_REPEATED_STATE`); `patches/llama.cpp` adds per-request `ctx_checkpoints` and `checkpoint_end`; `scripts/build-llama.sh` builds it into the ignored `.llamacpp/` on llama.cpp `6f41ac5`.
- Tetris: compact prompt, four profiles, no-model baselines and timing probes in [`examples/tetris/report`](../../../examples/tetris/report/README.md).
- Pages: https://hand-in.github.io/openjev-multimodal/models#max-qwen3-8-27b, /performance#repeated-state, /tetris and /demos/tetris/report/.

## Choosing the model

Qwen's Hugging Face organisation lists three Qwen3.8 models. Qwen3.8-27B is dense (27.8B parameters, the Qwen3.5 hybrid architecture, a vision tower, Apache-2.0) and runs on the existing llama.cpp support. Qwen3.8-Flash-Next activates about 6B of 125B parameters plus 51B n-gram embeddings; its smallest GGUF is 74.5 GB, too close to this Mac's GPU memory ceiling after the kernel panic of the same morning. Qwen3.8-2.4T-A95B is not a local model.

Prompt processing decides OpenJev's speed, and on the dense 27B it is compute-bound: llama-bench measured 189–201 tokens/s for UD-Q4_K_XL and 204–219 for Q4_0, in steps of 32 tokens, and today's llama.cpp master matches b9670. A published benchmark of an 8-bit build, 243 tokens/s at 1k context on an M4 Max, corresponds to about the same speed on this M3 Max. MTP heads speed up multi-token decoding, which a one-token readout never uses. UD-Q4_K_XL on llama.cpp was chosen: equal speed, image input through the existing projector, and the checkpoint control that the cache needs.

The Q8_0 GGUF was queued for download but did not finish that day: the local proxy stopped passing Hugging Face's file CDN and direct transfers ran at about 100 KB/s. A resuming download loop was left running.

## Evidence

Commit `451274e` passed the [package workflow](https://github.com/Hand-In/openjev-multimodal/actions/runs/35625800722) and the [documentation deployment](https://github.com/Hand-In/openjev-multimodal/actions/runs/35625800840). The English and Chinese Tetris, models and latency pages, the report, `replays.json` (four profiles, three prompts), the browser game and the max video returned HTTP 200. The browser replay played the max compact game in headless Chrome.

Every model ran alone on the GPU. max played 15 games (5 seeds × vision, text, compact) and a nine-presentation design study; fast, balanced and quality added 15 compact games and the compact design-study variant on the patched build. Python and JavaScript replays reproduce all 60 games, 2,884 decisions and 9,234 options. A fixed set of 23 requests (32 answers) gave identical decisions on stock llama.cpp b9670 and the patched build; the largest probability difference, 0.039, was on a single-question screenshot where neither the cache nor the patch applies.

## Results

- max clears 38.2 lines per game with the compact prompt at 0.73 s per decision (median of 234 calls), never tops out, and agrees with the reference evaluator on 81% of decisions (85% with the vision prompt).
- On the same 16 decisions: 1.93 s on stock llama.cpp, 0.83 s with the repeated-state cache, 0.66 s with the cache and the patch.
- quality with the compact prompt clears 38.2 lines, hole-free in 5 of 5 games, at 0.14 s per call. On this task max plays at quality's level; Qwen's published benchmarks rank it higher overall.
- Without a model, random picks among the same plans clear 14.3 lines and top out in 90 of 100 games; the reference evaluator clears 37.8.

## Completion audit

The sub-second figure includes each game's warm-up: the first two compact calls read the full prompt and prime the state (about 1.8 s each). The five fastest max text calls of the first run came from llama.cpp's RAM prompt cache, which still held identical prompts from the correctness check; that game was replayed on a fresh server with identical choices and replaces the original.

This is a 16-inch MacBook Pro in automatic power mode. After about 20 minutes of continuous load its GPU processed about 125 prompt tokens per second instead of 200, and the max text and vision games ran in that state; the controlled comparison above was measured after pauses. Five seeds per configuration is a small sample.
