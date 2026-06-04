from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

import uvicorn

from .app import create_web_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the local Personal Knowledge Agent Web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args(argv)

    try:
        app = create_web_app()
    except Exception as exc:
        print(f"Web 启动失败：{exc}", file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}"
    print(f"本地 Q&A 知识库 Web UI 已启动：{url}")
    if not args.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except Exception as exc:
        print(f"Web 服务运行失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
