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

## Vision path

Bounded images are EXIF-transposed, converted to RGB, resized and re-encoded. The API reads llama.cpp's actual media marker from `/props` and passes image data through its vision projector. This is native visual inference, not an OCR-only substitute.

Remote fetching and request-controlled file access are disabled. Treat model judgments as fallible application inputs: prompt injection can still affect predictions.

## References

| Project | Approach |
| --- | --- |
| [TypeSafe Jev](https://docs.typesafe.ai/api) | Proprietary hosted SystemOne |
| [openjev-sglang](https://github.com/ekzhang/openjev-sglang) | Text-only one-token Qwen readout with SGLang |
| [AlexWortega/openjev](https://huggingface.co/AlexWortega/openjev) | Qwen3.5 fine-tuned as a three-way NLI cross-encoder, including a vision checkpoint |
| This project | llama.cpp/Metal, text + images, one-token typed probabilities |

Published NLI model scores do not describe this implementation. Our chart uses our own Qwen3.6 API measurements. The [Hacker News discussion](https://news.ycombinator.com/item?id=49752041) motivated this project.
