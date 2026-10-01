"""Capture two actual local decisions and render a labeled replay GIF."""

import base64
import json
import shutil
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont


def font(size, bold=False):
    path = Path("/System/Library/Fonts/Supplemental") / ("Arial Bold.ttf" if bold else "Arial.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default(size)


def fixtures():
    Path("examples").mkdir(exist_ok=True)
    picture = Image.new("RGB", (640, 400), "#f5f3eb")
    draw = ImageDraw.Draw(picture)
    draw.rounded_rectangle((90, 30, 550, 370), radius=20, fill="white", outline="#dfe5d8", width=2)
    draw.ellipse((287, 59, 353, 125), fill="#e2f4d7")
    draw.line((306, 91, 317, 102, 339, 79), fill="#3b6d28", width=5)
    draw.text((320, 153), "Payment received", font=font(30, True), anchor="mm", fill="#22321d")
    draw.text((320, 194), "Your order is confirmed.", font=font(17), anchor="mm", fill="#6e7c65")
    draw.line((124, 229, 516, 229), fill="#e1e6dc", width=1)
    draw.text((125, 254), "ORDER  #1042", font=font(14), fill="#7d8876")
    draw.text((515, 254), "$48.00", font=font(18, True), anchor="ra", fill="#253920")
    draw.rounded_rectangle((125, 302, 515, 344), radius=8, fill="#243e1d")
    draw.text((320, 323), "Continue shopping", font=font(15), anchor="mm", fill="white")
    picture.save("examples/checkout.png")
    shutil.copy2("examples/checkout.png", "site/public/checkout.png")


def capture():
    fixtures()
    image = base64.b64encode(Path("examples/checkout.png").read_bytes()).decode()
    cases = [
        {
            "state": "I was charged twice. Please refund the duplicate payment.",
            "question": "Which team should handle this request?",
            "criteria": {
                "billing": "Payments and refunds",
                "technical": "Software bugs and integrations",
                "other": "Other requests",
            },
        },
        {
            "state": "Read the attached checkout screenshot.",
            "question": "What payment status is shown?",
            "criteria": {
                "paid": "Payment was successful",
                "pending": "Payment is still processing",
                "failed": "Payment failed",
            },
            "image": "/checkout.png",
        },
    ]
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=120, trust_env=False) as client:
        for case in cases:
            payload = {
                "model": "jev-latest",
                "state": case["state"],
                "questions": {
                    "decision": {
                        "type": "choice",
                        "instructions": case["question"],
                        "criteria": case["criteria"],
                    }
                },
            }
            if case.get("image"):
                payload["images"] = ["data:image/png;base64," + image]
            start = time.perf_counter()
            result = client.post("/v1/systemone", json=payload)
            result.raise_for_status()
            case.update(
                response=result.json(),
                elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                model=result.headers["x-openjev-model"],
                server_timing=result.headers["server-timing"],
            )
            print(case["question"], case["response"]["answers"]["decision"], flush=True)
            time.sleep(0.5)
    Path("site/public/demo.json").write_text(json.dumps(cases, indent=2))
    Path("benchmarks/demo.json").write_text(json.dumps(cases, indent=2))
    return cases


def artwork(cases):
    bg, accent, white, muted = "#101a14", "#b4f784", "#e7efdf", "#91a388"
    social = Image.new("RGB", (1200, 630), bg)
    d = ImageDraw.Draw(social)
    d.text((70, 58), "OPENJEV / MULTIMODAL", font=font(20, True), fill=accent)
    d.text((70, 154), "See. Decide.", font=font(88, True), fill=white)
    d.text((70, 253), "Stay local.", font=font(88, True), fill=accent)
    d.text((75, 393), "Text + images. Typed probabilities. Your Mac.", font=font(26), fill=muted)
    d.line((75, 484, 1125, 484), fill="#374931", width=2)
    d.text(
        (75, 522),
        "JEV-COMPATIBLE API  /  ONE OUTPUT TOKEN  /  OPEN SOURCE",
        font=font(18),
        fill=white,
    )
    social.save("site/public/social.png")
    social.save("assets/social.png")
    frames, durations = [], []
    for case in cases:
        for step in range(16):
            frame = Image.new("RGB", (900, 470), bg)
            d = ImageDraw.Draw(frame)
            d.text((34, 24), "OpenJev Multimodal", font=font(23, True), fill=white)
            d.text((865, 31), "RECORDED LOCAL RUN", font=font(11), anchor="ra", fill=accent)
            d.line((34, 69, 866, 69), fill="#31452a", width=1)
            if case.get("image"):
                im = Image.open("examples/checkout.png")
                im.thumbnail((382, 240))
                frame.paste(im, (35, 111))
            else:
                for i, line in enumerate(
                    ["I was charged twice.", "Please refund the", "duplicate payment."]
                ):
                    d.text((35, 144 + i * 38), line, font=font(25), fill=white)
            d.text((35, 363), "1 QUESTION  →  1 OUTPUT TOKEN", font=font(13), fill=accent)
            answer = case["response"]["answers"]["decision"]
            d.text((469, 102), answer["choice"], font=font(33, True), fill=accent)
            for i, (key, value) in enumerate(answer["probabilities"].items()):
                y = 177 + i * 56
                d.text((469, y), key, font=font(15), fill=white)
                d.text((862, y), f"{value * 100:.2f}%", font=font(15), anchor="ra", fill=accent)
                d.rounded_rectangle((469, y + 27, 862, y + 33), radius=3, fill="#2e3d29")
                width = max(1, int(393 * value * min(1, step / 10)))
                d.rounded_rectangle((469, y + 27, 469 + width, y + 33), radius=3, fill=accent)
            d.text(
                (469, 363),
                f"{case['elapsed_ms']:.0f} ms  ·  measured HTTP latency",
                font=font(13),
                fill=muted,
            )
            d.text(
                (35, 432),
                "Qwen3.6-35B-A3B · M3 Max · conditional probabilities",
                font=font(12),
                fill=muted,
            )
            frames.append(frame)
            durations.append(120 if step < 15 else 2100)
    frames[0].save(
        "assets/demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    artwork(capture())
