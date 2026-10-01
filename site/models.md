---
title: Qwen model choices and Apple Silicon performance
description: Choose Qwen3.5 0.8B, Qwen3.5 4B or Qwen3.6 35B-A3B for local typed inference. Read measured Mac performance and tradeoffs.
---

# Models and performance

Three pinned Qwen profiles provide the same API with a matching vision projector.

| Profile | Model | Quantization | Intended use |
| --- | --- | --- | --- |
| `fast` | Qwen3.5-0.8B | Q4_K_M | Small footprint, simple judgments |
| `balanced` (default) | Qwen3.5-4B | Q4_K_M | Everyday text and image decisions |
| `quality` | Qwen3.6-35B-A3B | UD-Q4_K_XL | Stronger knowledge on larger Macs |

The 35B mixture-of-experts model has approximately 3B active parameters, but all weights still occupy memory. Quality weights are approximately 23.3 GB plus a 0.9 GB projector. MTP tensors in this checkpoint are not used for speculative decoding: this API needs only the first output token.

Balanced is a practical starting point on a 16 GB or larger Mac. Use fast for a smaller footprint. For quality, leave substantial headroom beyond the weight size. **The verified machine is an M3 Max with 128 GB memory and a 40-core GPU. Smaller-machine memory minimums were not benchmarked.**

## Measured behavior

The published [180-case subset](./benchmarks) uses Qwen3.6-35B-A3B UD-Q4_K_XL, llama.cpp b9670, one slot, 8,192-token context and Metal. Median HTTP latency across these selected text cases was **281 ms**. This describes that workload, not a universal latency guarantee.

Fast and quality both completed real image classification. Balanced was downloaded and reached multimodal readiness. We avoided a large cross-model sweep to limit local load.

Longer prompts, multiple images, larger image budgets, concurrent evaluations, a cold model and other GPU work change latency. Model loading and downloads are excluded from per-request numbers.

## One-token inference

Each question performs prompt processing and a first-token readout. No reasoning trace or token-by-token JSON generation is needed. The API constructs typed JSON from measured label probabilities.

The model still reads the complete state. Questions run sequentially on one slot. Hybrid recurrent layers cannot roll back to an arbitrary cached position, so a multi-question request first evaluates the shared prefix once; each question then resumes from the backend checkpoint and processes only its own text. `x-openjev-cached-tokens` shows the reused tokens, and the response's `timing` object shows where the time went.

## Provenance

Exact revisions are pinned in [profiles.py](https://github.com/Hand-In/openjev-multimodal/blob/main/src/openjev/profiles.py).

- [Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-4B) and [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B): original model documentation.
- [Unsloth Qwen3.5 GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF): balanced weights and projector.
- [Qwen3.6 MTP GGUF](https://huggingface.co/havenoammo/Qwen3.6-35B-A3B-MTP-GGUF): quality weights; matching projector from [Unsloth](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF).

This repository's original code is MIT-licensed. Model weights and datasets retain their own licenses.
