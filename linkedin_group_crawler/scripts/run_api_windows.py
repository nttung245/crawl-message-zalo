from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import signal
import sys

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the FastAPI app on Windows.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def _make_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def main() -> None:
    args = _build_parser().parse_args()

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        loop="none",
        reload=False,
        log_level="info",
    )
    server = uvicorn.Server(config)

    loop = _make_loop()
    asyncio.set_event_loop(loop)

    if sys.platform == "win32":
        try:
            loop.add_signal_handler(signal.SIGINT, server.handle_exit, signal.SIGINT, None)  # type: ignore[arg-type]
        except NotImplementedError:
            pass
        try:
            loop.add_signal_handler(signal.SIGTERM, server.handle_exit, signal.SIGTERM, None)  # type: ignore[arg-type]
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(server.serve())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


if __name__ == "__main__":
    main()
