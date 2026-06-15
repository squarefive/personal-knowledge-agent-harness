from __future__ import annotations

import sys

from prompt_toolkit import PromptSession

from ...agent_factory import create_agent
from .cli_event_renderer import CliEventRenderer as CliRenderer
from ...config import load_config
from ...events import AgentEvent
from ...jsonl_logger import AsyncJsonlLogger
from ...permissions import ApprovalRequest

EXIT_COMMANDS = {"/exit", "/quit"}


def create_prompt_session() -> PromptSession:
    return PromptSession()


def prompt_user(session: PromptSession | None) -> str:
    if session is None:
        return input("你> ")
    return session.prompt("你> ")


def approve_tool_call(session: PromptSession | None, request: ApprovalRequest) -> bool:
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
    renderer = CliRenderer(stream=sys.stdout)
    event_logger = AsyncJsonlLogger()
    rendered_final_answer = False

    def handle_event(event: AgentEvent) -> None:
        nonlocal rendered_final_answer
        try:
            renderer.render(event)
            if event.event_type == "final_answer_generated":
                rendered_final_answer = True
        except Exception as exc:
            print(f"CLI 渲染失败：{exc}", file=sys.stderr)
        if event.event_type != "answer_delta":
            event_logger.write(event)

    try:
        config = load_config()
        prompt_session = create_prompt_session() if sys.stdin.isatty() else None
        agent = create_agent(
            config,
            event_sink=handle_event,
            approval_callback=lambda request: approve_tool_call(prompt_session, request),
        )
    except Exception as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1

    print("本地 Q&A 知识库 Agent 已启动。输入 /exit 或 /quit 退出。")
    try:
        while True:
            try:
                raw_input = prompt_user(prompt_session)
            except EOFError:
                print("已退出。")
                return 0

            user_input = raw_input.strip()
            if not user_input:
                continue
            if user_input in EXIT_COMMANDS:
                print("已退出。")
                return 0

            rendered_final_answer = False
            try:
                answer = agent.run(raw_input)
            except Exception as exc:
                print(f"Agent> 模型服务暂时不可用，本轮没有完成。你可以稍后重试。错误：{exc}")
                continue
            if not rendered_final_answer:
                print(f"Agent> {answer}")
    finally:
        event_logger.close()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["web"]:
        from ..web.web_main import main as web_main

        return web_main(args[1:])
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
