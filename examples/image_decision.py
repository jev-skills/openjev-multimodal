"""Usage: uv run python examples/image_decision.py examples/checkout.png"""

import argparse
import base64
import json
import mimetypes
from pathlib import Path

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image", type=Path)
parser.add_argument("--url", default="http://127.0.0.1:8000")
args = parser.parse_args()
mime = mimetypes.guess_type(args.image.name)[0] or "image/png"
encoded = base64.b64encode(args.image.read_bytes()).decode()
result = httpx.post(
    args.url + "/v1/systemone",
    json={
        "model": "jev-latest",
        "state": "Read the attached checkout screenshot.",
        "images": [f"data:{mime};base64,{encoded}"],
        "questions": {
            "decision": {
                "type": "choice",
                "instructions": "What payment status is shown?",
                "criteria": {
                    "paid": "Payment was successful",
                    "pending": "Payment is still processing",
                    "failed": "Payment failed",
                },
            }
        },
    },
    timeout=120,
)
result.raise_for_status()
print(json.dumps(result.json(), indent=2))
