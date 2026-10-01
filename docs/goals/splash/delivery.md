# Delivery receipt

Researched and verified on September 21, 2026. Commit dates are fixed at October 1, 2026, as for the rest of the history.

## What Splash is

[Splash](https://github.com/incoai/splash) (read at `7e3c67e`) is open source under Apache-2.0: a Python HTTP server over a C++ and Objective-C++ runtime with hand-shaped Metal kernels, built for two models (Qwen3.8-27B and Qwen3.6-35B-A3B). Its [Qwen3.8-27B package](https://huggingface.co/incoai/Qwen3.8-27B-Splash) holds the mlx-community 4-bit target, a DFlash 2 draft, the vision encoder and the tokenizer as fixed-layout binaries.

Why it is fast, from the source and the launch post:

- **Decode is speculative.** A five-layer DFlash 2 draft reads five of the target's layers and proposes 7 tokens per step; the target verifies them in one pass. That gives 74 tokens/s on an M5 Pro. OpenJev reads one token per question, so this part does not apply.
- **Prefill uses Metal 4.** Kernels are generated for the model's exact shapes with MetalPerformancePrimitives `matmul2d` on 4-bit (`uint4b`) tensors, which reach the M5's neural accelerators: 363 tokens/s on a 16-core M5 Pro, 1.2× the next engine.
- **The cache follows prefixes.** Attention state lives in 32-token pages indexed by content; Gated DeltaNet state is snapshotted at prefix boundaries (periodic checkpoints, prefixes shared with other requests, the end of the replayable prompt) and kept in an LRU. A replayed 32K prompt starts in 282 ms, 7.3× the next engine.
- It also serves `/v1/systemone` typed judgments, reading answer-slot logits after a fixed system instruction, like OpenJev.

## Why it cannot run here

The kernels need Metal 4: `MTL4CommandQueue`, MetalPerformancePrimitives tensor ops, `uint4b_format` tensors and sparse buffer mapping, guarded by `@available(macOS 26.4, *)`. This Mac stays on macOS 15, whose Metal 3 compiler cannot build them, so neither the engine nor its kernels port. Even on macOS 26.4, an M3 has no neural accelerators: the tensor ops would run on the same simdgroup matrix units that llama.cpp already drives. llama.cpp's Qwen3.8-27B prefill here adds about 140 ms per 32 tokens, around 12 TFLOPS, close to what this GPU can do.

## What was applied

- **State snapshots at the prefix boundary** already existed: the repeated-state cache and the llama.cpp patch's `checkpoint_end`.
- **Several prefixes at once.** The llama.cpp that `scripts/build-llama.sh` builds keeps earlier prompts in host memory with their checkpoints. Four 800-token states used in rotation answered in 0.11 s each on Qwen3.5-4B, against 0.69 s with llama.cpp b9670, which re-read every state. `openjev serve` now uses that build automatically when it has been built (`OPENJEV_LLAMA_SERVER` or `--llama-server` override it).
- **8-bit weights prefill faster here.** llama-bench on this M3 Max: Q8_0 took 338, 496 and 626 ms for 64, 96 and 128 tokens against 361, 536 and 680 ms for UD-Q4_K_XL. A compact Tetris decision fell from 0.66 s to 0.63 s (16 decisions, `report/probes/patched-cache-q8.json`), and all 32 answers of the fixed check set matched. `--quant Q8_0` selects it; the profile keeps UD-Q4_K_XL, which every published max result used.
- Not applied: speculative decoding (one-token readout) and a system-instruction-first prompt, which would change the prompt behind every published measurement.

## Faster downloads

Measured from this Mac: Hugging Face and hf-mirror.com delivered about 0.1 MB/s, and the local proxy on port 1082 refused connections. ModelScope delivered 12 MB/s on one connection and 52, 73 and 82 MB/s on 4, 8 and 16. ModelScope mirrors every unsloth GGUF repository the profiles use, `mlx-community/Qwen3.8-27B-8bit`, `incoai/Qwen3.8-27B-Splash` and `Qwen/Qwen3.8-27B`; not the quality weights (`havenoammo`) or Jundot's oQ8e-mtp.

`openjev download` and `serve` take `--source modelscope` (or `OPENJEV_MODEL_SOURCE`), `--connections` and `--quant`. Files download as parallel, resumable 32 MB ranges, are checked against the SHA-256 pinned in `profiles.py` and are installed into the Hugging Face cache; a file missing from one hub comes from the other. The fast profile (737 MB) arrived and verified in 13.5 s. The 29 GB Q8_0 took about six minutes; one range failed after its retries, the resumed pass fetched it, and the file verified.
