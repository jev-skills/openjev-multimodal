---
title: Qwen model choices and Apple Silicon performance
description: Choose Qwen3.5 0.8B, Qwen3.5 4B, Qwen3.6 35B-A3B or Qwen3.8 27B for local typed inference. Measured Mac performance and tradeoffs.
---

# Models and performance

Four pinned Qwen profiles serve the same API, each with a matching vision projector.

| Profile | Model | Quantization | Intended use |
| --- | --- | --- | --- |
| `fast` | Qwen3.5-0.8B | Q4_K_M | Small footprint, simple judgments |
| `balanced` (default) | Qwen3.5-4B | Q4_K_M | Everyday text and image decisions |
| `quality` | Qwen3.6-35B-A3B | UD-Q4_K_XL | Stronger knowledge on larger Macs |
| `max` | Qwen3.8-27B | UD-Q4_K_XL | The strongest judgment |

Balanced is a practical start on a 16 GB or larger Mac; fast suits a smaller footprint. Quality weights are about 23.3 GB, max weights 17.6 GB, each plus a 0.9 GB projector. **The verified machine is an M3 Max with 128 GB memory and a 40-core GPU. Smaller-machine minimums were not benchmarked.**

## Max: Qwen3.8-27B

Qwen3.8-27B is a dense model: every prompt token runs all 27 billion parameters, about 5 ms per token on an M3 Max. A full 305-token decision in the [Tetris demo](./tetris) takes 1.9 s. When consecutive requests repeat their state, the API keeps it cached and reads only each new question: 0.7 s.

For that speed, build llama.cpp with OpenJev's patches once; `openjev serve` then uses it automatically:

```bash
scripts/build-llama.sh
uv run openjev serve --profile max
```

Stock llama.cpp runs the same profile, about 0.2 s slower per cached request. `--quant Q8_0` loads the 8-bit weights (29 GB): on an M3 Max they process short prompts about 5% faster than UD-Q4_K_XL, and all 32 answers of our check set matched. MTP heads and speculative decoding do not help: OpenJev reads one output token.

## Measured behavior

The published [180-case subset](./benchmarks) uses Qwen3.6-35B-A3B UD-Q4_K_XL, llama.cpp b9670, one slot, an 8,192-token context and Metal. Median HTTP latency across these selected text cases was **281 ms**. It describes that workload, not every input. [Latency →](./performance)

Longer prompts, more images, larger image budgets, concurrent evaluations, a cold model and other GPU work change latency. Downloads and model loading are excluded from per-request numbers.

## One-token inference

Each question performs prompt processing and a first-token readout. No reasoning trace or token-by-token JSON generation is needed. The API builds typed JSON from measured label probabilities.

The model still reads the complete state. Questions run one after another on one slot. Hybrid recurrent layers cannot roll back to an arbitrary cached position, so the API evaluates a shared state once, and each question resumes from that checkpoint with only its own text. `x-openjev-cached-tokens` shows the reused tokens; the response's `timing` object shows where the time went.

## Provenance

Exact revisions are pinned in [profiles.py](https://github.com/jev-skills/openjev-multimodal/blob/main/src/openjev/profiles.py).

- [Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-4B), [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) and [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B): original model documentation.
- Unsloth GGUF [0.8B](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF), [4B](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF) and [27B](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF): fast, balanced and max weights and projectors.
- [Qwen3.6 MTP GGUF](https://huggingface.co/havenoammo/Qwen3.6-35B-A3B-MTP-GGUF): quality weights; matching projector from [Unsloth](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF).

This repository's original code is MIT-licensed. Model weights and datasets keep their own licenses.
