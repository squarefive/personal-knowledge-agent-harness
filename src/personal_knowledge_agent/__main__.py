from __future__ import annotations

import sys

from .agent_loop import AgentLoop
from .config import AgentConfig, load_config
from .llm_client import DeepSeekClient
from .sqlite_store import SQLiteStore
from .tool_dispatcher import ToolDispatcher
from .tools import KnowledgeTools

EXIT_COMMANDS = {"/exit", "/quit"}


def create_agent(config: AgentConfig) -> AgentLoop:
    store = SQLiteStore(config.knowledge_db_path)
    tools = KnowledgeTools(store)
    dispatcher = ToolDispatcher(tools)
    llm = DeepSeekClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    return AgentLoop(llm=llm, tools=tools, dispatcher=dispatcher)


def run_cli() -> int:
    try:
        config = load_config()
        agent = create_agent(config)
    except Exception as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1

    print("本地 Q&A 知识库 Agent 已启动。输入 /exit 或 /quit 退出。")
    while True:
        try:
            user_input = input("你> ").strip()
        except EOFError:
            print("已退出。")
            return 0

        if not user_input:
            continue
        if user_input in EXIT_COMMANDS:
            print("已退出。")
            return 0

        answer = agent.run(user_input)
        print(f"Agent> {answer}")


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
