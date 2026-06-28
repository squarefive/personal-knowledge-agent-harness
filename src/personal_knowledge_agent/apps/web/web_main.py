from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

import uvicorn

from ...agent_bootstrap import load_config
from ...agent_observability import AgentEventJsonlLogger
from .cloud_dependencies import close_web_cloud_dependencies, create_web_cloud_dependencies
from .web_app import create_web_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the cloud-only Personal Knowledge Agent Web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args(argv)

    event_logger = AgentEventJsonlLogger()
    cloud_dependencies = None
    try:
        config = load_config()
        cloud_dependencies = create_web_cloud_dependencies(config)
        app = create_web_app(
            config=config,
            auth_service=cloud_dependencies.auth_service,
            email_sender=cloud_dependencies.email_sender,
            user_tool_factory=cloud_dependencies.user_tool_factory,
            cloud_session_repository=cloud_dependencies.session_repository,
            event_logger=event_logger,
        )

        @app.on_event("shutdown")
        def close_cloud_dependencies() -> None:
            close_web_cloud_dependencies(cloud_dependencies)
    except Exception as exc:
        close_web_cloud_dependencies(cloud_dependencies)
        event_logger.close()
        print(f"Web 启动失败：{exc}", file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}"
    print(f"云端个人 Q&A 知识库 Web UI 已启动：{url}")
    if not args.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except Exception as exc:
        print(f"Web 服务运行失败：{exc}", file=sys.stderr)
        return 1
    finally:
        event_logger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
