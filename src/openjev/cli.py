"""One command owns model download, the inference backend and the HTTP API lifecycle."""

import argparse
import json
import os
import platform
import signal
import sys

import uvicorn

from . import backends
from .api import create_app
from .config import Settings

WITH_BACKEND = ("serve", "download")  # commands that take a backend and its options


def chosen(argv: list[str]) -> backends.BackendPlugin:
    """The backend named by --backend or OPENJEV_BACKEND; it adds its own options."""
    probe = argparse.ArgumentParser(add_help=False)
    probe.add_argument("command", nargs="?")
    probe.add_argument("--backend", default=os.environ.get("OPENJEV_BACKEND", backends.DEFAULT))
    known, _ = probe.parse_known_args(argv)
    return backends.load(known.backend if known.command in WITH_BACKEND else backends.DEFAULT)


def parser(plugin: backends.BackendPlugin) -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="openjev", description="Local multimodal typed decisions")
    sub = root.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Download a pinned model and start the local API")
    download = sub.add_parser("download", help="Cache pinned model and projector weights")
    for name, command in zip(WITH_BACKEND, (serve, download), strict=True):
        command.add_argument(
            "--backend",
            default=plugin.name,
            help=f"inference backend: {', '.join(backends.names())} "
            f"(default: {backends.DEFAULT}, or OPENJEV_BACKEND)",
        )
        default = plugin.default_profile if plugin.default_profile in plugin.profiles else None
        command.add_argument(
            "--profile", choices=plugin.profiles, default=default, required=default is None
        )
        if name == "serve":
            command.add_argument("--host", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8000)
            command.add_argument("--context", type=int, default=8192)
            command.add_argument("--image-tokens", type=int, default=512)
        plugin.add_arguments(command, name)
    sub.add_parser("doctor", help="Show local prerequisites without downloading models")
    sub.add_parser("schema", help="Print the OpenAPI schema without starting inference")
    return root


def serve(args, plugin: backends.BackendPlugin):
    settings = Settings(
        backend=plugin.name,
        model_name=plugin.profiles[args.profile],
        max_input_tokens=args.context,
        image_token_budget=args.image_tokens,
    )
    previous_term = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        with plugin.launch(args, settings) as backend:
            print(f"Playground: http://{args.host}:{args.port}/playground", flush=True)
            app = create_app(settings, backend)
            uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    finally:
        signal.signal(signal.SIGTERM, previous_term)


def doctor() -> dict:
    report = {
        "python": sys.version.split()[0],
        "system": platform.system(),
        "architecture": platform.machine(),
        "apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
        "api_key_configured": bool(os.getenv("OPENJEV_API_KEY")),
        "backends": {},
    }
    for name in backends.names():
        try:
            plugin = backends.load(name)
        except ValueError as exc:
            report["backends"][name] = {"error": str(exc)}
            continue
        report["backends"][plugin.name] = {
            "summary": plugin.summary,
            **plugin.doctor(),
            "profiles": dict(plugin.profiles),
        }
    return report


def main(argv: list[str] | None = None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        plugin = chosen(argv)
        args = parser(plugin).parse_args(argv)
        if args.command == "serve":
            serve(args, plugin)
        elif args.command == "download":
            print(json.dumps(plugin.download(args), indent=2))
        elif args.command == "schema":
            print(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False))
        elif args.command == "doctor":
            print(json.dumps(doctor(), indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"openjev: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
