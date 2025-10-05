"""Command line entrypoint for rendering service."""

from __future__ import annotations

import argparse
import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ReelToolkit renderer service")
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Enable autoreload (dev only)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    uvicorn.run(
        "renderer_service.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=False,
    )


if __name__ == "__main__":
    main()
