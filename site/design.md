---
title: Probability readout and Jev compatibility
description: How OpenJev computes complete one-token label distributions, preserves the SystemOne API, and differs from other OpenJev projects.
---

# Design and compatibility

OpenJev Multimodal independently implements the Jev-style SystemOne interface and adds local image input. It is not affiliated with TypeSafe and does not contain proprietary Jev weights.

## Compatible interface

The request envelope, Noul/Choice/Score types, named answers and probability fields follow the public interface. `jev-latest` selects your local Qwen model. Structured instructions and criteria are supported.

One synthetic request containing all three types was sent to the official online API using the local `typesafe-ai` skill. HTTP 200 from `jev-1.13.0` confirmed the wire shape. This was **not an accuracy or speed comparison**.

Predictions, local limits, confidence and usage accounting differ. We support 2–255 Choice options, up to 64 Score levels and 64 questions. TypeSafe currently documents up to 10 Score levels. See `/v1/limits` for actual local limits.

## Probability readout

1. Validate and sanitize state and images.
2. Apply the backend's native chat template with thinking disabled.
3. Map options to verified single-token labels.
4. Add the **same +100 logit bias** to each label. Request one token and post-sampling probabilities, without top-k/top-p/min-p truncation or repetition penalties.
5. Require every candidate in the returned list and normalize over those candidates. Missing values cause a 502.
6. Compute typed answers directly from the distribution.

For selected labels, a shared bias cancels:

```text
exp(logit_i + b) / sum_selected exp(logit_j + b)
  = exp(logit_i) / sum_selected exp(logit_j)
```

This holds up to floating-point rounding. Bias brings candidates into the returned list while preserving relative odds. Completeness is checked; missing-label probabilities are never invented. Grammar-only readout was unsuitable because the verified llama.cpp build can expose probabilities before lazy grammar filtering.

Choice returns the argmax. Score is `sum(index * probability)`. Confidence is `1 − normalized entropy`. Wording and option order affect predictions; these are not calibrated correctness guarantees.

## Latency path

Every question costs a prefill of its full prompt. Qwen3.5, Qwen3.6 and Qwen3.8 are hybrid models: their recurrent layers cannot roll back to an arbitrary cached position, so llama.cpp re-read the shared state, images included, for every question. Requests with two or more questions now evaluate the shared prefix once; llama.cpp checkpoints it, and each question resumes from there with only its own text. A screenshot with four questions takes less than half the time. Decisions stay the same; probabilities move by at most 0.067 because the prefix runs as its own batch.

The API also fills a verified chat-template skeleton locally instead of calling `/apply-template` (about 9 ms) on every request, and resizes an oversized image once, straight to the vision encoder's size. [Measurements →](./performance)

## Vision path

Bounded images are EXIF-transposed, converted to RGB and re-encoded; images larger than the vision budget are resized once to the backend's own target size (a 32-pixel grid within `--image-tokens`). The API reads llama.cpp's actual media marker from `/props` and passes image data through its vision projector. This is native visual inference, not an OCR-only substitute.

Remote fetching and request-controlled file access are disabled. Treat model judgments as fallible application inputs: prompt injection can still affect predictions.

## Backends

The API reaches its model through a small contract in [`openjev.backends`](https://github.com/jev-skills/openjev-multimodal/blob/main/src/openjev/backends/__init__.py). A backend loads the model, finds 255 single-token answer labels, renders the chat template, counts tokens, primes a shared prefix and returns each label's probability after a prompt. The evaluator does the rest: prompts, scoring, limits and the caching policy. llama.cpp implements the contract over localhost HTTP.

A plugin package tells `openjev serve` how to run its backend: its options, profiles and download step, and a launch that yields the backend and cleans up afterwards. It registers under the `openjev.backends` entry-point group:

```toml
[project.entry-points."openjev.backends"]
mine = "my_package:plugin"
```

Names match without case or punctuation, so `llamacpp` also selects llama.cpp. `openjev doctor` reports a plugin that fails to import; the others keep working.

## References

| Project | Approach |
| --- | --- |
| [TypeSafe Jev](https://docs.typesafe.ai/api) | Proprietary hosted SystemOne |
| [openjev-sglang](https://github.com/ekzhang/openjev-sglang) | Text-only one-token Qwen readout with SGLang |
| [AlexWortega/openjev](https://huggingface.co/AlexWortega/openjev) | Qwen3.5 fine-tuned as a three-way NLI cross-encoder, including a vision checkpoint |
| This project | llama.cpp/Metal, text + images, one-token typed probabilities |

Published NLI model scores do not describe this implementation. Our chart uses our own Qwen3.6 API measurements. The [Hacker News discussion](https://news.ycombinator.com/item?id=49752041) motivated this project.
