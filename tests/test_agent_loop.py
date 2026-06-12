import copy

from personal_knowledge_agent.agent_loop import AgentLoop
from personal_knowledge_agent.agent_memory import MemoryExtractor, MemoryIndexStore, MemoryStore
from personal_knowledge_agent.qa_store import SQLiteStore
from personal_knowledge_agent.schemas import LLMResponse, ToolCall
from personal_knowledge_agent.session_memory import ContextCompactor, SessionMetadataStore, SessionTranscript
from personal_knowledge_agent.tools import KnowledgeTools, ToolDispatcher


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, *, messages, tools, system_prompt):
        self.calls.append(
            {
                "messages": copy.deepcopy(messages),
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
                            "category": "Agent 开发",
                        },
                    )
                ]
            ),
            LLMResponse(text="已保存。"),
        ]
    )
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        event_sink=events.append,
    )

    answer = loop.run("帮我记一条知识")

    assert answer.startswith("已保存。")
    assert "来源：" in answer
    assert "原始问题: 什么是最小闭环？" in answer
    assert "source_type: manual_qa" in answer
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


def test_agent_loop_does_not_reuse_previous_turn_sources(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
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
                            "category": "Agent 开发",
                        },
                    )
                ]
            ),
            LLMResponse(text="已保存。"),
            LLMResponse(text="可以用 set 去重。"),
        ]
    )
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
    )

    first_answer = loop.run("帮我记一条知识")
    second_answer = loop.run("Python list 怎么去重？")

    assert "来源：" in first_answer
    assert "来源：" not in second_answer
    assert "什么是最小闭环？" not in second_answer


def test_agent_loop_executes_dangerous_tool_after_approval(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    saved = knowledge_tools.save_qa_card(
        {
            "question": "旧问题？",
            "answer": "旧答案。",
            "summary": "旧摘要。",
            "keywords": ["旧"],
            "category": "Agent 开发",
        }
    )
    dispatcher = ToolDispatcher(knowledge_tools)
    approvals = []
    fake_llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="delete_qa_card",
                        arguments={"card_id": saved["card_id"]},
                    )
                ]
            ),
            LLMResponse(text="已删除。"),
        ]
    )
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        approval_callback=lambda request: approvals.append(request) is None or True,
    )

    answer = loop.run("删除这张卡片")

    assert answer == "已删除。"
    assert approvals[0].tool_name == "delete_qa_card"
    assert knowledge_tools.read_qa_card({"card_id": saved["card_id"]})["error_code"] == "not_found"


def test_agent_loop_denies_dangerous_tool_without_execution(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    saved = knowledge_tools.save_qa_card(
        {
            "question": "问题？",
            "answer": "答案。",
            "summary": "摘要。",
            "keywords": ["关键词"],
            "category": "Agent 开发",
        }
    )
    dispatcher = ToolDispatcher(knowledge_tools)
    fake_llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="delete_qa_card",
                        arguments={"card_id": saved["card_id"]},
                    )
                ]
            ),
            LLMResponse(text="操作未执行。"),
        ]
    )
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        approval_callback=lambda request: False,
    )

    answer = loop.run("删除这张卡片")
    second_messages = fake_llm.calls[1]["messages"]

    assert answer == "操作未执行。"
    assert knowledge_tools.read_qa_card({"card_id": saved["card_id"]})["ok"] is True
    assert "permission_denied" in second_messages[-1]["content"]


def test_agent_loop_safe_tool_does_not_request_approval(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    approvals = []
    fake_llm = FakeLLM(
        [
            LLMResponse(tool_calls=[ToolCall(id="call_1", name="list_recent_cards", arguments={"limit": 5})]),
            LLMResponse(text="没有最近卡片。"),
        ]
    )
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        approval_callback=lambda request: approvals.append(request) is None or True,
    )

    loop.run("列出最近卡片")

    assert approvals == []


def test_agent_loop_injects_memory_context_using_recent_messages(tmp_path):
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
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    fake_llm = FakeLLM([LLMResponse(text="继续。")])
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        memory_index_store=MemoryIndexStore(tmp_path),
        memory_store=MemoryStore(tmp_path),
        messages=[{"role": "user", "content": "继续 Agent memory 管理设计，实现 turn-start memory 选择"}],
    )

    loop.run("继续")

    system_prompt = fake_llm.calls[0]["system_prompt"]
    assert "可用 Agent memory 索引" in system_prompt
    assert "本轮已加载的相关 Agent memory" in system_prompt
    assert "Q&A 知识库和 Agent memory 必须分开。" in system_prompt


def test_agent_loop_emits_context_compacted_event_for_large_tool_result(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
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
        context_compactor=ContextCompactor(tmp_path, threshold_chars=1),
        event_sink=events.append,
    )

    loop.run("列出最近卡片")

    compact_events = [event for event in events if event.event_type == "context_compacted"]
    assert len(compact_events) == 1
    record = compact_events[0].payload["compact_record"]
    assert record["artifact_path"].startswith(".sessions/default/artifacts/")
    assert record["summary"]
    assert record["relevance"]
    assert (tmp_path / record["artifact_path"]).exists()


def test_agent_loop_persists_messages_to_transcript(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    transcript = SessionTranscript(tmp_path)
    metadata_store = SessionMetadataStore(tmp_path, model="test-model")
    events = []
    fake_llm = FakeLLM([LLMResponse(text="第一轮回答。"), LLMResponse(text="第二轮回答。")])
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        transcript=transcript,
        metadata_store=metadata_store,
        event_sink=events.append,
    )

    loop.run("第一轮")
    loop.run("第二轮")

    assert fake_llm.calls[1]["messages"][0]["content"] == "第一轮"
    assert fake_llm.calls[1]["messages"][1]["content"] == "第一轮回答。"
    assert fake_llm.calls[1]["messages"][2]["content"] == "第二轮"
    assert [message["content"] for message in transcript.load_messages()] == [
        "第一轮",
        "第一轮回答。",
        "第二轮",
        "第二轮回答。",
    ]
    metadata = metadata_store.load_or_create()
    assert metadata.event_count == 4
    assert metadata.message_count == 4


def test_agent_loop_emits_memory_candidates(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    events = []
    fake_llm = FakeLLM([LLMResponse(text="好的。")])
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
        memory_extractor=MemoryExtractor(),
        event_sink=events.append,
    )

    loop.run("记住：以后回答我先给结论。")

    event_types = [event.event_type for event in events]
    assert "memory_candidates_generated" in event_types
    candidates_event = next(event for event in events if event.event_type == "memory_candidates_generated")
    assert candidates_event.payload["candidates"][0]["type"] == "user"
    assert candidates_event.payload["candidates"][0]["write_policy"] == "needs_confirmation"
