---
title: Multimodal examples — images, routing and rubrics
description: Send local images and chat content to the Jev-compatible API. Use Python and JavaScript to turn vision and text into typed decisions.
---

# Text + vision examples

## Classify a local image

Images stay on your machine when calling the local API. Inline data URLs avoid remote fetching and server-side filesystem access.

```python
import base64
from pathlib import Path
import httpx

image = base64.b64encode(Path("screenshot.png").read_bytes()).decode()
response = httpx.post("http://127.0.0.1:8000/v1/systemone", json={
    "model": "jev-latest",
    "state": "A checkout screenshot. Read its payment status.",
    "images": ["data:image/png;base64," + image],
    "questions": {
        "decision": {
            "type": "choice",
            "instructions": "What is the payment status shown?",
            "criteria": {
                "paid": "Payment was successful",
                "pending": "Payment is still processing",
                "failed": "Payment failed"
            }
        }
    }
}, timeout=120)
response.raise_for_status()
print(response.json()["answers"]["decision"])
```

Run the repository example:

```bash
uv run python examples/image_decision.py examples/checkout.png
```

## Multimodal chat state

```json
{
  "model": "jev-latest",
  "state": {
    "messages": [{
      "role": "user",
      "content": [
        { "type": "text", "text": "Read this checkout screen." },
        { "type": "image_url", "image_url": { "url": "data:image/png;base64,..." } }
      ]
    }]
  },
  "questions": {
    "paid": {
      "type": "noul",
      "instructions": "Does the screen confirm successful payment?"
    }
  }
}
```

Replace `...` with real base64. PNG, JPEG and WebP are supported. HTTP image URLs, file URLs, animation, raw audio and native video uploads are rejected. For frame-based judgments, extract a few video frames yourself, send ordered images and include timestamps in state. This is not motion-aware video understanding.

## Call from JavaScript

```js
const response = await fetch("http://127.0.0.1:8000/v1/systemone", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "jev-latest",
    state: { ticket: "The payment failed three times.", account: "business" },
    questions: {
      route: {
        type: "choice",
        instructions: "Choose the support team.",
        criteria: { billing: "Payments", product: "Product features", other: "Other issues" }
      },
      urgency: {
        type: "score",
        instructions: "How time-sensitive is the ticket?",
        criteria: ["Routine", "Needs prompt attention", "Service unavailable"]
      }
    }
  })
});
if (!response.ok) throw new Error(await response.text());
const { answers } = await response.json();
console.log(answers.route.choice, answers.urgency.score);
```

Run this in Node.js or a same-origin app. The static site does not access localhost or proxy credentials. Use the bundled local playground for browser experimentation.

## Compose decisions

Keep arithmetic and execution in code. Ask narrowly defined questions, inspect distributions, and evaluate thresholds on your own data. Include `other` or `none` when candidates are not exhaustive.

Use one Noul per independent condition when multiple labels may apply. Choice compares competing alternatives. Score is an expected ordinal index and can fall between levels.
