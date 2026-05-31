from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession

from .agent_loop import AgentLoop
from .cli_renderer import CliRenderer
from .config import AgentConfig, load_config
from .context_compactor import ContextCompactor
from .events import AgentEvent
from .jsonl_logger import AsyncJsonlLogger
from .llm_client import DeepSeekClient
from .memory_extractor import MemoryExtractor
from .memory_index import MemoryIndexStore
from .memory_store import MemoryStore
from .session_metadata import SessionMetadataStore
from .session_restore import SessionRestore
from .session_summarizer import SessionSummarizer
from .session_transcript import SessionTranscript
from .sqlite_store import SQLiteStore
from .tool_dispatcher import ToolDispatcher
from .tools import KnowledgeTools

EXIT_COMMANDS = {"/exit", "/quit"}


def create_agent(config: AgentConfig, event_sink: Callable[[AgentEvent], None] | None = None) -> AgentLoop:
    store = SQLiteStore(config.knowledge_db_path)
    workspace_root = Path.cwd()
    llm = DeepSeekClient(
        api_key=config.deepseek_api_key,
        model=config.deepseek_model,
    )
    transcript = SessionTranscript(workspace_root)
    metadata_store = SessionMetadataStore(workspace_root, model=config.deepseek_model)
    restore_result = SessionRestore(
        transcript=transcript,
        metadata_store=metadata_store,
        summarizer=SessionSummarizer(llm),
    ).restore()
    metadata = metadata_store.load_or_create()
    memory_index_store = MemoryIndexStore(workspace_root)
    memory_store = MemoryStore(workspace_root)
    tools = KnowledgeTools(
        store,
        memory_index_store=memory_index_store,
        memory_store=memory_store,
    )
    dispatcher = ToolDispatcher(tools)
    return AgentLoop(
        llm=llm,
        tools=tools,
        dispatcher=dispatcher,
        memory_index_store=memory_index_store,
        memory_store=memory_store,
        messages=restore_result.messages,
        transcript=transcript,
        metadata_store=metadata_store,
        context_compactor=ContextCompactor(workspace_root, artifacts_dir=metadata.artifacts_dir),
        memory_extractor=MemoryExtractor(),
        event_sink=event_sink,
    )


def create_prompt_session() -> PromptSession:
    return PromptSession()


def prompt_user(session: PromptSession | None) -> str:
    if session is None:
        return input("你> ")
    return session.prompt("你> ")


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
        event_logger.write(event)

    try:
        config = load_config()
        agent = create_agent(config, event_sink=handle_event)
        prompt_session = create_prompt_session() if sys.stdin.isatty() else None
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
            answer = agent.run(raw_input)
            if not rendered_final_answer:
                print(f"Agent> {answer}")
    finally:
        event_logger.close()


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
