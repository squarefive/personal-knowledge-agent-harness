from personal_knowledge_agent.agent_loop import AgentLoop
from personal_knowledge_agent.context_compactor import ContextCompactor
from personal_knowledge_agent.memory_index import MemoryIndexStore
from personal_knowledge_agent.memory_store import MemoryStore
from personal_knowledge_agent.schemas import LLMResponse, SessionSummary, ToolCall
from personal_knowledge_agent.session_store import SessionStore
from personal_knowledge_agent.sqlite_store import SQLiteStore
from personal_knowledge_agent.tool_dispatcher import ToolDispatcher
from personal_knowledge_agent.tools import KnowledgeTools


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, *, messages, tools, system_prompt):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "system_prompt": system_prompt,
            }
        )
        return self.responses.pop(0)


def test_agent_loop_executes_tool_call_and_returns_final_answer(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    events = []
    fake_llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="save_qa_card",
                        arguments={
                            "question": "什么是最小闭环？",
                            "answer": "能保存、检索、回答并引用来源。",
                            "summary": "最小闭环包含保存、检索、回答和来源。",
                            "keywords": ["最小闭环", "来源"],
                        },
                    )
                ]
            ),
            LLMResponse(text="已保存，来源是新建的 card_id。"),
        ]
    )
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        event_sink=events.append,
    )

    answer = loop.run("帮我记一条知识")

    assert answer == "已保存，来源是新建的 card_id。"
    assert len(fake_llm.calls) == 2
    second_messages = fake_llm.calls[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert "card_id" in second_messages[-1]["content"]
    event_types = [event.event_type for event in events]
    assert event_types == [
        "user_input_received",
        "llm_call_started",
        "llm_call_finished",
        "tool_call_started",
        "tool_call_finished",
        "llm_call_started",
        "llm_call_finished",
        "evidence_checked",
        "final_answer_generated",
    ]
    assert events[0].payload["user_input"] == "帮我记一条知识"
    assert events[3].payload["input"]["question"] == "什么是最小闭环？"
    assert "card_id" in events[4].payload["output"]


def test_agent_loop_returns_final_answer_without_tool_call(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    events = []
    fake_llm = FakeLLM([LLMResponse(text="本地知识库中没有找到足够依据。")])
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        event_sink=events.append,
    )

    assert loop.run("未知问题") == "本地知识库中没有找到足够依据。"
    assert [event.event_type for event in events] == [
        "user_input_received",
        "llm_call_started",
        "llm_call_finished",
        "evidence_checked",
        "final_answer_generated",
    ]


def test_agent_loop_injects_memory_context_using_session_summary(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "\n".join(
            [
                "# Memory Index",
                "",
                "| name | type | description | path |",
                "|---|---|---|---|",
                "| memory-design | project | Agent memory 管理设计 | .memory/memory-design.md |",
            ]
        ),
        encoding="utf-8",
    )
    (memory_dir / "memory-design.md").write_text(
        "\n".join(
            [
                "---",
                'name: "memory-design"',
                'type: "project"',
                'description: "Agent memory 管理设计"',
                'updated_at: "2026-05-31"',
                'source_type: "user_decision"',
                "---",
                "",
                "Q&A 知识库和 Agent memory 必须分开。",
            ]
        ),
        encoding="utf-8",
    )
    session_store = SessionStore(tmp_path)
    session_store.write_current(
        SessionSummary(
            current_goal="继续 Agent memory 管理设计",
            next_steps=["实现 turn-start memory 选择"],
        )
    )
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    fake_llm = FakeLLM([LLMResponse(text="继续。")])
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        memory_index_store=MemoryIndexStore(tmp_path),
        memory_store=MemoryStore(tmp_path),
        session_store=session_store,
    )

    loop.run("继续")

    system_prompt = fake_llm.calls[0]["system_prompt"]
    assert "可用 Agent memory 索引" in system_prompt
    assert "本轮已加载的相关 Agent memory" in system_prompt
    assert "Q&A 知识库和 Agent memory 必须分开。" in system_prompt
    assert "current_goal: 继续 Agent memory 管理设计" in system_prompt


def test_agent_loop_emits_context_compacted_event_for_large_tool_result(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    session_store = SessionStore(tmp_path)
    events = []
    fake_llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="list_recent_cards",
                        arguments={"limit": 5},
                    )
                ]
            ),
            LLMResponse(text="没有最近卡片。"),
        ]
    )
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        context_compactor=ContextCompactor(session_store, threshold_chars=1),
        event_sink=events.append,
    )

    loop.run("列出最近卡片")

    compact_events = [event for event in events if event.event_type == "context_compacted"]
    assert len(compact_events) == 1
    record = compact_events[0].payload["compact_record"]
    assert record["artifact_path"].startswith(".session/artifacts/")
    assert record["summary"]
    assert record["relevance"]
    assert (tmp_path / record["artifact_path"]).exists()
