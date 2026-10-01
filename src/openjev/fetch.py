"""Pinned model files from Hugging Face or ModelScope, verified and cached.

Both hubs serve byte-identical files; ModelScope is often far faster from mainland China.
Files are fetched as parallel, resumable byte ranges, checked against the SHA-256 pinned
in profiles.py, and installed into the Hugging Face cache, so later runs find them
offline whichever hub they came from.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from .profiles import Artifact

SOURCES = ("huggingface", "modelscope")
CHUNK = 32 << 20  # bytes per ranged request
ATTEMPTS = 8  # per byte range; transient network errors back off up to 30 s
PASSES = 3  # resumed passes over the missing ranges before trying the other hub


def cached(artifact: Artifact) -> Path | None:
    """The file in the Hugging Face cache at the pinned revision, if present."""
    from huggingface_hub import try_to_load_from_cache

    found = try_to_load_from_cache(artifact.repo, artifact.filename, revision=artifact.revision)
    return Path(found) if isinstance(found, str) else None


def url(artifact: Artifact, source: str) -> str:
    if source == "modelscope":
        return f"https://modelscope.cn/models/{artifact.repo}/resolve/master/{artifact.filename}"
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    return f"{endpoint}/{artifact.repo}/resolve/{artifact.revision}/{artifact.filename}"


def headers(source: str) -> dict[str, str]:
    token = os.environ.get("HF_TOKEN") if source == "huggingface" else None
    return {"Authorization": f"Bearer {token}"} if token else {}


def fetch(
    artifact: Artifact,
    source: str = "huggingface",
    connections: int = 8,
    log: Callable[[str], None] = print,
) -> Path:
    """Return a local path to `artifact`, downloading it from `source` if needed."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}")
    found = cached(artifact)
    if found:
        return found
    if not (artifact.size and artifact.sha256):
        # Unpinned files keep the hub client's own download and verification.
        from huggingface_hub import hf_hub_download

        return Path(hf_hub_download(artifact.repo, artifact.filename, revision=artifact.revision))
    order = [source] + [s for s in SOURCES if s != source]
    errors = []
    for hub in order:
        try:
            return download(artifact, hub, connections, log)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            errors.append(f"{hub}: {exc}")
            log(f"{artifact.filename}: {hub} failed ({exc}); trying the next source")
    raise RuntimeError(f"Cannot download {artifact.filename}: " + "; ".join(errors))


def download(artifact: Artifact, source: str, connections: int, log) -> Path:
    from huggingface_hub.constants import HF_HUB_CACHE

    repo_dir = Path(HF_HUB_CACHE) / ("models--" + artifact.repo.replace("/", "--"))
    blob = repo_dir / "blobs" / artifact.sha256
    target = repo_dir / "snapshots" / artifact.revision / artifact.filename
    if not blob.exists():
        blob.parent.mkdir(parents=True, exist_ok=True)
        part = blob.with_name(blob.name + ".part")
        for attempt in range(PASSES):
            try:
                ranges(
                    url(artifact, source), headers(source), part, artifact.size, connections, log
                )
                break
            except httpx.TransportError as exc:
                if attempt == PASSES - 1:
                    raise
                log(f"{artifact.filename}: {exc}; resuming the missing ranges")
        log(f"{artifact.filename}: verifying SHA-256")
        if sha256(part) != artifact.sha256:
            part.unlink()
            Path(str(part) + ".json").unlink(missing_ok=True)
            raise ValueError(f"{source} served different bytes than the pinned revision")
        os.replace(part, blob)
        Path(str(part) + ".json").unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.symlink_to(os.path.relpath(blob, target.parent))
    return target


def ranges(address: str, extra: dict, part: Path, size: int, connections: int, log) -> None:
    """Fill `part` with `size` bytes from `address` using parallel, resumable ranges."""
    state = Path(str(part) + ".json")
    done = set(json.loads(state.read_text())) if state.exists() and part.exists() else set()
    with open(part, "ab"):
        pass
    os.truncate(part, size)
    chunks = [i for i in range(-(-size // CHUNK)) if i not in done]
    lock, fetched, started = threading.Lock(), [0], time.monotonic()
    name = part.name.removesuffix(".part")[:12]

    def one(index: int) -> None:
        first = index * CHUNK
        last = min(size, first + CHUNK) - 1
        for attempt in range(ATTEMPTS):
            try:
                with httpx.Client(timeout=60, follow_redirects=True) as client:
                    response = client.get(
                        address, headers={**extra, "Range": f"bytes={first}-{last}"}
                    )
                    response.raise_for_status()
                    body = response.content
                if response.status_code != 206 or len(body) != last - first + 1:
                    raise httpx.HTTPError(f"expected {last - first + 1} bytes, got {len(body)}")
                with open(part, "r+b") as handle:
                    os.pwrite(handle.fileno(), body, first)
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or attempt == ATTEMPTS - 1:
                    raise  # a missing or forbidden file will not appear on retry
                time.sleep(min(2**attempt, 30))
            except httpx.HTTPError:
                if attempt == ATTEMPTS - 1:
                    raise
                time.sleep(min(2**attempt, 30))
        with lock:
            done.add(index)
            fetched[0] += len(body)
            state.write_text(json.dumps(sorted(done)))
            complete = len(done) * CHUNK
            if len(done) % max(1, connections) == 0 or complete >= size:
                rate = fetched[0] / max(time.monotonic() - started, 1e-3) / 1e6
                progress = f"{min(complete, size) / 1e9:.1f} of {size / 1e9:.1f} GB"
                log(f"{name}: {progress}, {rate:.0f} MB/s")

    with concurrent.futures.ThreadPoolExecutor(max(1, connections)) as pool:
        for future in concurrent.futures.as_completed([pool.submit(one, i) for i in chunks]):
            future.result()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(8 << 20):
            digest.update(block)
    return digest.hexdigest()
