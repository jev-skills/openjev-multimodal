import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import __version__
from .backends import Backend, load
from .config import Settings
from .errors import APIError
from .schema import Evaluation, Result, Timing
from .service import Evaluator

RECEIVED = "openjev.received"  # ASGI scope key: perf_counter() when the request arrived
PROCESSING = b"x-openjev-processing-ms"


def since(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def timed(send, received: float):
    """Wrap an ASGI `send` so the response reports processing time unless it already does."""

    async def wrapped(message):
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            if not any(name.lower() == PROCESSING for name, _ in headers):
                headers.append((PROCESSING, f"{since(received):.2f}".encode()))
                message = {**message, "headers": headers}
        await send(message)

    return wrapped


class Guard:
    """Bound streamed bodies before JSON parsing, authenticate private routes and report
    server processing time on every /v1/ response, including errors."""

    def __init__(self, app, settings: Settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        received = scope[RECEIVED] = time.perf_counter()
        if scope["path"].startswith("/v1/"):
            send = timed(send, received)

        key = self.settings.api_key
        if key and scope["path"].startswith("/v1/"):
            supplied = dict(scope["headers"]).get(b"authorization", b"")
            if not secrets.compare_digest(supplied, f"Bearer {key.get_secret_value()}".encode()):
                return await JSONResponse(
                    {"error": {"message": "Missing or invalid API key."}},
                    401,
                    headers={"WWW-Authenticate": "Bearer"},
                )(scope, receive, send)
        if scope["method"] == "POST":
            body = bytearray()
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    return
                body.extend(event.get("body", b""))
                if len(body) > self.settings.max_body_bytes:
                    return await JSONResponse(
                        {"error": {"message": "Request body exceeds the size limit."}},
                        413,
                    )(scope, receive, send)
                if not event.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            return await self.app(scope, replay, send)
        return await self.app(scope, receive, send)


def create_app(settings: Settings | None = None, backend: Backend | None = None) -> FastAPI:
    """The API over `backend`, or over the one `settings.backend` names, unlaunched."""
    settings = settings or Settings()
    if backend is None:
        backend = load(settings.backend).create(settings)
    evaluator = Evaluator(settings, backend)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await backend.initialize()
            yield
        finally:
            await backend.close()

    app = FastAPI(
        title="OpenJev Multimodal",
        version=__version__,
        lifespan=lifespan,
        description=(
            "Jev-compatible typed decisions from local text and images. "
            "One output token per question. Conditional label probabilities; "
            "independent open-model implementation, not TypeSafe's proprietary Jev weights."
        ),
    )
    app.add_middleware(Guard, settings=settings)

    @app.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError):
        return JSONResponse(
            {"error": {"message": str(exc)}},
            status_code=exc.status,
            headers={"Retry-After": "1"} if exc.status in {503, 529} else {},
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        issues = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"error": {"message": "Invalid request."}, "detail": issues}, 422)

    @app.get("/", include_in_schema=False)
    async def home():
        return RedirectResponse("/playground")

    @app.get("/playground", include_in_schema=False)
    async def playground():
        return HTMLResponse(Path(__file__).with_name("playground.html").read_text())

    @app.get("/health/live", tags=["Status"])
    async def live():
        return {"status": "ok"}

    @app.get("/health", tags=["Status"])
    async def health():
        ready = await backend.ready()
        return JSONResponse(
            {
                "status": "ok" if ready else "unavailable",
                "model": backend.model,
                "multimodal": backend.vision,
                "backend": backend.name,
                "backend_build": backend.build,
                "weights": backend.weights,
            },
            status_code=200 if ready else 503,
        )

    @app.get("/v1/models", tags=["Discovery"])
    async def models():
        names = list(dict.fromkeys(["jev-latest", "openjev-latest", backend.model]))
        return {
            "models": [
                {
                    "name": name,
                    "description": f"Local {backend.model}; "
                    + ("text + images" if backend.vision else "text only"),
                    "release_date": "2026-10-01",
                }
                for name in names
            ],
            "object": "list",
            "data": [
                {"id": name, "object": "model", "owned_by": "openjev-multimodal"} for name in names
            ],
            "capabilities": ["text", "images"] if backend.vision else ["text"],
        }

    @app.get("/v1/limits", tags=["Discovery"])
    async def limits():
        return {
            "max_answers_per_question": 255,
            "max_score_levels": 64,
            "max_questions": 64,
            "max_body_bytes": settings.max_body_bytes,
            "max_input_tokens": backend.context_size,
            "max_total_input_tokens": settings.max_total_input_tokens,
            "max_concurrent_requests": settings.max_concurrent_requests,
            "max_images": settings.max_images,
            "image_max_edge": settings.image_max_edge,
            "request_timeout_seconds": settings.request_timeout,
        }

    @app.post(
        "/v1/systemone",
        response_model=Result,
        response_model_exclude_none=True,
        tags=["SystemOne"],
        summary="Evaluate state",
    )
    async def evaluate(payload: Evaluation, request: Request):
        handler = time.perf_counter()
        received = request.scope.get(RECEIVED, handler)

        async def disconnected():
            while True:
                if (await request.receive())["type"] == "http.disconnect":
                    return

        job = asyncio.create_task(evaluator.evaluate(payload))
        watcher = asyncio.create_task(disconnected())
        try:
            await asyncio.wait({job, watcher}, return_when=asyncio.FIRST_COMPLETED)
            if not job.done():
                raise APIError("Client disconnected.", 499)
            result, stats = await job
            timing = Timing(
                processing_ms=round(since(received), 2),
                parse_ms=round((handler - received) * 1000, 2),
                prepare_ms=round(stats.prepare_ms, 2),
                queue_ms=round(stats.queue_ms, 2),
                inference_ms=round(stats.inference_ms, 2),
            )
            body = result.model_dump(exclude={"timing"})
            if settings.response_timing:
                body["timing"] = timing.model_dump()
            return JSONResponse(
                body,
                headers={
                    "x-typesafe-request-id": stats.request_id,
                    "x-openjev-model": stats.model,
                    "x-openjev-cached-tokens": str(stats.cached_tokens),
                    "x-openjev-elapsed-ms": f"{stats.elapsed_ms:.2f}",
                    "x-openjev-processing-ms": f"{timing.processing_ms:.2f}",
                    "Server-Timing": (
                        f"parse;dur={timing.parse_ms:.2f}, "
                        f"prepare;dur={timing.prepare_ms:.2f}, "
                        f"queue;dur={timing.queue_ms:.2f}, "
                        f"inference;dur={timing.inference_ms:.2f}, "
                        f"compute;dur={stats.compute_ms:.2f}, "
                        f"total;dur={timing.processing_ms:.2f}"
                    ),
                },
            )
        finally:
            for task in (job, watcher):
                if not task.done():
                    task.cancel()
            await asyncio.gather(job, watcher, return_exceptions=True)

    return app
