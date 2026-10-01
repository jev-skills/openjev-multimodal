"""One command owns model download, local backend and HTTP API lifecycle."""

import argparse
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import uvicorn

from .api import create_app
from .config import Settings
from .profiles import PROFILES


def parser():
    root = argparse.ArgumentParser(prog="openjev", description="Local multimodal typed decisions")
    sub = root.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Download a pinned model and start the local API")
    serve.add_argument("--profile", choices=PROFILES, default="balanced")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--backend-port", type=int, default=18081)
    serve.add_argument(
        "--connect", help="Connect to an existing llama.cpp server instead of launching"
    )
    serve.add_argument("--model-file", type=Path, help="Use existing GGUF weights")
    serve.add_argument("--mmproj-file", type=Path, help="Use existing matching vision projector")
    serve.add_argument("--llama-server", default="llama-server")
    serve.add_argument("--context", type=int, default=8192)
    serve.add_argument("--image-tokens", type=int, default=512)
    serve.add_argument("--threads", type=int, default=4, help="Bound CPU threads (default: 4)")
    serve.add_argument("--startup-timeout", type=float, default=300)
    download = sub.add_parser("download", help="Cache pinned model and projector weights")
    download.add_argument("--profile", choices=PROFILES, default="balanced")
    sub.add_parser("doctor", help="Show local prerequisites without downloading models")
    sub.add_parser("schema", help="Print the OpenAPI schema without starting inference")
    return root


def weights(profile, model_file=None, mmproj_file=None):
    from huggingface_hub import hf_hub_download

    paths = []
    for supplied, filename, repo, revision in (
        (model_file, profile.weights, profile.repo, profile.revision),
        (
            mmproj_file,
            profile.projector,
            profile.projector_repo or profile.repo,
            profile.projector_revision or profile.revision,
        ),
    ):
        if supplied is not None:
            path = supplied.expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"Missing model file: {path}")
            paths.append(str(path))
        else:
            print(f"Preparing {repo}/{filename} …", flush=True)
            paths.append(hf_hub_download(repo, filename, revision=revision))
    return paths


def serve(args):
    profile = PROFILES[args.profile]
    settings = Settings(
        model_name=profile.model,
        max_input_tokens=args.context,
        image_token_budget=args.image_tokens,
        backend_url=args.connect or f"http://127.0.0.1:{args.backend_port}",
    )
    process = None
    log = None
    previous_term = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        if not args.connect:
            executable = shutil.which(args.llama_server)
            if not executable:
                raise ValueError("llama-server is missing. On macOS run: brew install llama.cpp")
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", args.backend_port)) == 0:
                    raise ValueError(
                        f"Backend port {args.backend_port} is occupied; "
                        "use --connect or choose --backend-port."
                    )
            model, projector = weights(profile, args.model_file, args.mmproj_file)
            logs = Path.home() / ".cache" / "openjev-multimodal"
            logs.mkdir(parents=True, exist_ok=True)
            log_path = logs / f"backend-{args.backend_port}.log"
            log = log_path.open("a")
            command = [
                executable,
                "-m",
                model,
                "--mmproj",
                projector,
                "--host",
                "127.0.0.1",
                "--port",
                str(args.backend_port),
                "--alias",
                profile.model,
                "-c",
                str(args.context),
                "-np",
                "1",
                "-ngl",
                "99",
                "--jinja",
                "--reasoning",
                "off",
                "--chat-template-kwargs",
                '{"enable_thinking":false}',
                "--image-max-tokens",
                str(args.image_tokens),
                "-t",
                str(args.threads),
                "-tb",
                str(args.threads),
            ]
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            print(f"Loading {profile.model} on Metal. Backend log: {log_path}", flush=True)
            deadline = time.monotonic() + args.startup_timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"llama-server exited ({process.returncode}); see {log_path}"
                    )
                try:
                    with httpx.Client(timeout=1, trust_env=False) as client:
                        if client.get(settings.backend_url + "/health").status_code == 200:
                            break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError(f"Model startup timed out; see {log_path}")
        print(f"Playground: http://{args.host}:{args.port}/playground", flush=True)
        uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False)
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if log:
            log.close()
        signal.signal(signal.SIGTERM, previous_term)


def main():
    args = parser().parse_args()
    try:
        if args.command == "serve":
            serve(args)
        elif args.command == "download":
            print(json.dumps(weights(PROFILES[args.profile]), indent=2))
        elif args.command == "schema":
            print(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False))
        elif args.command == "doctor":
            print(
                json.dumps(
                    {
                        "python": sys.version.split()[0],
                        "system": platform.system(),
                        "architecture": platform.machine(),
                        "llama_server": shutil.which("llama-server"),
                        "apple_silicon": platform.system() == "Darwin"
                        and platform.machine() == "arm64",
                        "api_key_configured": bool(os.getenv("OPENJEV_API_KEY")),
                        "profiles": {k: v.model for k, v in PROFILES.items()},
                    },
                    indent=2,
                )
            )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"openjev: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
