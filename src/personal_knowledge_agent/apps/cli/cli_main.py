from __future__ import annotations

import sys
from typing import Any

from ...tool_runtime import ApprovalRequest
from .constants import CliConstants as cli_constants


def create_prompt_session() -> None:
    return None


def prompt_user(session: Any | None) -> str:
    return input("你> ") if session is None else session.prompt("你> ")


def approve_tool_call(session: Any | None, request: ApprovalRequest) -> bool:
    print("高风险工具请求需要确认。")
    print(f"工具: {request.tool_name}")
    print(f"原因: {request.reason}")
    print(f"参数: {request.arguments}")
    if session is None:
        answer = input("允许执行？输入 yes 允许：")
    else:
        answer = session.prompt("允许执行？输入 yes 允许：")
    return answer.strip().lower() == "yes"


def run_cli() -> int:
    print("本地 CLI Agent runtime 已移除；请使用 `personal-knowledge-agent web` 启动 cloud-only Web runtime。")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == [cli_constants.WEB_COMMAND]:
        from ..web.web_main import main as web_main

        return web_main(args[1:])
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
