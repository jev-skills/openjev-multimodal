"""Preserve application state while compiling compact classification questions."""

import json
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .errors import APIError
from .media import sanitize_image
from .schema import Choice, Evaluation, Noul, Question

MEDIA_MARKER = "<__media__>"


def text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def state_messages(request: Evaluation, settings: Settings) -> tuple[list[dict], list[str]]:
    candidate = request.state
    if isinstance(candidate, dict) and set(candidate) == {"messages"}:
        candidate = candidate["messages"]
    is_chat = (
        isinstance(candidate, list)
        and bool(candidate)
        and all(isinstance(m, dict) and "role" in m for m in candidate)
    )
    if is_chat:
        messages = candidate
    elif isinstance(request.state, str) or not settings.compact_json:
        messages = [{"role": "user", "content": text(request.state)}]
    else:
        compact = json.dumps(request.state, ensure_ascii=False, separators=(",", ":"))
        messages = [{"role": "user", "content": compact}]
    result, images = [], []

    def add_image(url: str) -> str:
        if len(images) >= settings.max_images:
            raise APIError(f"At most {settings.max_images} images are allowed.")
        images.append(sanitize_image(url, settings))
        return MEDIA_MARKER

    for message in messages:
        if message["role"] not in {"user", "assistant", "system", "tool"}:
            raise APIError("Unsupported chat message role.")
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    raise APIError("Chat content parts must be objects.")
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif part.get("type") == "image_url":
                    value = part.get("image_url")
                    if not isinstance(value, dict) or not isinstance(value.get("url"), str):
                        raise APIError("image_url requires an object with a data-URL 'url'.")
                    parts.append(add_image(value["url"]))
                else:
                    raise APIError("Supported content types are text and image_url.")
            content = "\n".join(parts)
        elif content is None:
            content = ""
        elif not isinstance(content, str):
            raise APIError("Chat content must be text or an array of content parts.")
        # A literal marker cannot be allowed to consume an unrelated image.
        expected = len(images) - sum(m["content"].count(MEDIA_MARKER) for m in result)
        if content.count(MEDIA_MARKER) != expected:
            raise APIError("The reserved media marker is not allowed in input text.")
        result.append({**message, "content": content})
    if request.images:
        result.append({"role": "user", "content": "\n".join(add_image(x) for x in request.images)})
    return result, images


def choices(question: Question) -> list[tuple[str, str]]:
    if isinstance(question, Noul):
        return [
            ("true", text(question.criteria.positive)),
            ("false", text(question.criteria.negative)),
        ]
    if isinstance(question, Choice):
        return [
            (key, key if value is None else text(value)) for key, value in question.criteria.items()
        ]
    return [(str(i), text(value)) for i, value in enumerate(question.criteria)]


@dataclass
class Branch:
    key: str
    question: Question
    prompt: str
    options: list[str]
    labels: list[tuple[str, int]]


def question_text(question: Question, labels: list[tuple[str, int]]) -> str:
    lines = ["Question: " + text(question.instructions or "Choose the best matching option."), ""]
    for (_, description), (label, _) in zip(choices(question), labels, strict=True):
        lines.append(f"{label}: " + description.replace("\n", "\n  "))
    return "\n".join(lines)
