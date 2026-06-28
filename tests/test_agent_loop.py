import copy

from personal_knowledge_agent.agent_runtime import AgentLoopRunner
from personal_knowledge_agent.agent_context.agent_profile_memory import (
    AgentMemoryCandidateExtractor,
    MemoryDocument,
)
from personal_knowledge_agent.llm_clients import LLMResponse, LLMUsage
from personal_knowledge_agent.llm_clients.deepseek_chat_client import LLMContextLengthExceeded
from personal_knowledge_agent.tool_runtime import ToolCall
from personal_knowledge_agent.agent_tools import AgentMemoryToolHandlers, QAKnowledgeToolHandlers
from personal_knowledge_agent.tool_runtime import ToolDispatcher
from tests.fakes import (
    InMemoryMemoryStore,
    InMemoryMetadataStore,
    InMemoryQACardStore,
    InMemoryRuntimeContextCompactor,
    InMemoryToolResultCompactor,
    InMemoryTranscript,
)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, *, messages, tools, system_prompt, on_text_delta=None):
        self.calls.append(
            {
                "messages": copy.deepcopy(messages),
                "tools": tools,
                "system_prompt": system_prompt,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if response.text and on_text_delta is not None:
            on_text_delta(response.text)
        return response


class FakeSummarizer:
    max_retries = 3

    def __init__(self, summary="summary"):
        self.summary = summary
        self.calls = []

    def summarize(self, messages):
        self.calls.append(messages)
        return self.summary, 1


def create_dispatcher(tmp_path, qa_tools):
    memory_store = InMemoryMemoryStore()
    memory_tools = AgentMemoryToolHandlers(
        memory_index_repository=memory_store,
        memory_document_repository=memory_store,
    )
    return ToolDispatcher(qa_tools, memory_tools)


def test_agent_loop_executes_tool_call_and_returns_final_answer(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
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
    loop = AgentLoopRunner(
        llm=fake_llm,
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
        "answer_delta",
        "llm_call_finished",
        "evidence_checked",
        "final_answer_generated",
    ]
    assert events[0].payload["user_input"] == "帮我记一条知识"
    assert events[3].payload["input"]["question"] == "什么是最小闭环？"
    assert "card_id" in events[4].payload["output"]


def test_agent_loop_executes_full_library_duplicate_detection_once(tmp_path):
    store = InMemoryQACardStore()
    store.save_card(
        question="DeepSeek API key 应该如何配置？",
        answer="把 DeepSeek API key 放到环境变量中。",
        summary="DeepSeek API key 配置方式。",
        keywords=["DeepSeek", "API key", "配置"],
        category="Agent 开发",
    )
    store.save_card(
        question="DeepSeek 的 API key 怎么配置？",
        answer="DeepSeek API key 应配置到环境变量。",
        summary="配置 DeepSeek API key。",
        keywords=["DeepSeek", "API key", "配置"],
        category="Agent 开发",
    )
    knowledge_tools = QAKnowledgeToolHandlers(store)
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    fake_llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="detect_duplicate_cards",
                        arguments={"scope": "all", "mode": "manual"},
                    )
                ]
            ),
            LLMResponse(text="发现 1 组疑似重复。"),
        ]
    )
    loop = AgentLoopRunner(llm=fake_llm, dispatcher=dispatcher)

    answer = loop.run("本地有没有重复的卡片呢")

    assert answer == "发现 1 组疑似重复。"
    assert len(fake_llm.calls) == 2
    tool_messages = [
        message
        for message in fake_llm.calls[1]["messages"]
        if message["role"] == "tool"
    ]
    assert len(tool_messages) == 1
    assert "duplicate_groups" in tool_messages[0]["content"]
    assert "checked_count" in tool_messages[0]["content"]


def test_agent_loop_returns_final_answer_without_tool_call(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    events = []
    fake_llm = FakeLLM([LLMResponse(text="本地知识库中没有找到足够依据。")])
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        event_sink=events.append,
    )

    assert loop.run("未知问题") == "本地知识库中没有找到足够依据。"
    assert [event.event_type for event in events] == [
        "user_input_received",
        "llm_call_started",
        "answer_delta",
        "llm_call_finished",
        "evidence_checked",
        "final_answer_generated",
    ]


def test_agent_loop_does_not_reuse_previous_turn_sources(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
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
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
    )

    first_answer = loop.run("帮我记一条知识")
    second_answer = loop.run("Python list 怎么去重？")

    assert "来源：" in first_answer
    assert "来源：" not in second_answer
    assert "什么是最小闭环？" not in second_answer


def test_agent_loop_executes_dangerous_tool_after_approval(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    saved = knowledge_tools.save_qa_card(
        {
            "question": "旧问题？",
            "answer": "旧答案。",
            "summary": "旧摘要。",
            "keywords": ["旧"],
            "category": "Agent 开发",
        }
    )
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
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
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        approval_callback=lambda request: approvals.append(request) is None or True,
    )

    answer = loop.run("删除这张卡片")

    assert answer == "已删除。"
    assert approvals[0].tool_name == "delete_qa_card"
    assert knowledge_tools.read_qa_card({"card_id": saved["card_id"]})["error_code"] == "not_found"


def test_agent_loop_executes_merge_tool_after_approval(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    first = knowledge_tools.save_qa_card(
        {
            "question": "问题一？",
            "answer": "答案一。",
            "summary": "摘要一。",
            "keywords": ["合并"],
            "category": "Agent 开发",
        }
    )
    second = knowledge_tools.save_qa_card(
        {
            "question": "问题二？",
            "answer": "答案二。",
            "summary": "摘要二。",
            "keywords": ["合并"],
            "category": "Agent 开发",
        }
    )
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    approvals = []
    fake_llm = FakeLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="merge_qa_cards",
                        arguments={
                            "card_ids": [first["card_id"], second["card_id"]],
                            "question": "合并问题？",
                            "answer": "合并答案。",
                            "summary": "合并摘要。",
                            "keywords": ["合并"],
                            "category": "Agent 开发",
                        },
                    )
                ]
            ),
            LLMResponse(text="已合并。"),
        ]
    )
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        approval_callback=lambda request: approvals.append(request) is None or True,
    )

    answer = loop.run("合并这两张卡片")

    assert answer == "已合并。"
    assert approvals[0].tool_name == "merge_qa_cards"
    assert knowledge_tools.read_qa_card({"card_id": first["card_id"]})["error_code"] == "not_found"
    assert knowledge_tools.read_qa_card({"card_id": second["card_id"]})["error_code"] == "not_found"


def test_agent_loop_denies_dangerous_tool_without_execution(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    saved = knowledge_tools.save_qa_card(
        {
            "question": "问题？",
            "answer": "答案。",
            "summary": "摘要。",
            "keywords": ["关键词"],
            "category": "Agent 开发",
        }
    )
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
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
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        approval_callback=lambda request: False,
    )

    answer = loop.run("删除这张卡片")
    second_messages = fake_llm.calls[1]["messages"]

    assert answer == "操作未执行。"
    assert knowledge_tools.read_qa_card({"card_id": saved["card_id"]})["ok"] is True
    assert "permission_denied" in second_messages[-1]["content"]


def test_agent_loop_safe_tool_does_not_request_approval(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    approvals = []
    fake_llm = FakeLLM(
        [
            LLMResponse(tool_calls=[ToolCall(id="call_1", name="list_recent_cards", arguments={"limit": 5})]),
            LLMResponse(text="没有最近卡片。"),
        ]
    )
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        approval_callback=lambda request: approvals.append(request) is None or True,
    )

    loop.run("列出最近卡片")

    assert approvals == []


def test_agent_loop_injects_memory_context_using_recent_messages(tmp_path):
    memory_store = InMemoryMemoryStore(
        [
            MemoryDocument(
                name="memory-design",
                type="project",
                description="Agent memory 管理设计",
                path="postgres://memory/memory-design",
                updated_at="2026-05-31",
                source_type="user_decision",
                source_ref=None,
                content="Q&A 知识库和 Agent memory 必须分开。",
            )
        ]
    )
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    fake_llm = FakeLLM([LLMResponse(text="继续。")])
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        memory_index_store=memory_store,
        memory_store=memory_store,
        messages=[{"role": "user", "content": "继续 Agent memory 管理设计，实现 turn-start memory 选择"}],
    )

    loop.run("继续")

    system_prompt = fake_llm.calls[0]["system_prompt"]
    assert "可用 Agent memory 索引" in system_prompt
    assert "本轮已加载的相关 Agent memory" in system_prompt
    assert "Q&A 知识库和 Agent memory 必须分开。" in system_prompt


def test_agent_loop_injects_at_most_three_memory_document_contents(tmp_path):
    memory_store = InMemoryMemoryStore(
        [
            MemoryDocument(
                name=f"memory-{index}",
                type="project",
                description=f"memory compact 规则 {index}",
                path=f"postgres://memory/{index}",
                updated_at="2026-06-20",
                source_type="user_decision",
                source_ref=None,
                content=f"正文内容 {index}",
            )
            for index in range(5)
        ]
    )
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    fake_llm = FakeLLM([LLMResponse(text="继续。")])
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        memory_index_store=memory_store,
        memory_store=memory_store,
    )

    loop.run("继续 memory compact 规则")

    system_prompt = fake_llm.calls[0]["system_prompt"]
    injected_contents = [f"正文内容 {index}" for index in range(5) if f"正文内容 {index}" in system_prompt]
    assert len(injected_contents) == 3


def test_agent_loop_emits_context_compacted_event_for_large_tool_result(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
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
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        context_compactor=InMemoryToolResultCompactor(threshold_chars=1),
        event_sink=events.append,
    )

    loop.run("列出最近卡片")

    compact_events = [event for event in events if event.event_type == "context_compacted"]
    assert len(compact_events) == 1
    record = compact_events[0].payload["compact_record"]
    assert record["artifact_path"].startswith("postgres://artifacts/")
    assert record["summary"]
    assert record["relevance"]


def test_agent_loop_persists_messages_to_transcript(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    transcript = InMemoryTranscript()
    metadata_store = InMemoryMetadataStore(model="test-model")
    events = []
    fake_llm = FakeLLM([LLMResponse(text="第一轮回答。"), LLMResponse(text="第二轮回答。")])
    loop = AgentLoopRunner(
        llm=fake_llm,
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
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    events = []
    fake_llm = FakeLLM([LLMResponse(text="好的。")])
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        memory_extractor=AgentMemoryCandidateExtractor(),
        event_sink=events.append,
    )

    loop.run("记住：以后回答我先给结论。")

    event_types = [event.event_type for event in events]
    assert "memory_candidates_generated" in event_types
    candidates_event = next(event for event in events if event.event_type == "memory_candidates_generated")
    assert candidates_event.payload["candidates"][0]["type"] == "user"
    assert candidates_event.payload["candidates"][0]["write_policy"] == "needs_confirmation"


def test_agent_loop_compacts_before_next_run_when_last_prompt_usage_exceeds_threshold(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    events = []
    summarizer = FakeSummarizer(summary="压缩后的 summary")
    fake_llm = FakeLLM(
        [
            LLMResponse(text="第一轮回答。", usage=LLMUsage(prompt_tokens=80, total_tokens=90)),
            LLMResponse(text="第二轮回答。"),
        ]
    )
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        runtime_context_compactor=InMemoryRuntimeContextCompactor(
            summarizer=summarizer,
            recent_messages_count=1,
        ),
        context_window_tokens=100,
        event_sink=events.append,
    )

    loop.run("第一轮")
    loop.run("第二轮")

    assert summarizer.calls
    assert fake_llm.calls[1]["messages"] == [{"role": "user", "content": "第二轮"}]
    assert "# Runtime Session Context" in fake_llm.calls[1]["system_prompt"]
    assert "压缩后的 summary" in fake_llm.calls[1]["system_prompt"]
    prompt_usage_events = [event for event in events if event.event_type == "prompt_usage_updated"]
    assert prompt_usage_events[0].payload == {"prompt_usage_ratio": 0.8}
    compaction_events = [
        event for event in events if event.event_type.startswith("runtime_context_compaction_")
    ]
    assert [event.event_type for event in compaction_events] == [
        "runtime_context_compaction_started",
        "runtime_context_compaction_finished",
    ]
    assert compaction_events[0].payload == {
        "reason": "usage_threshold",
        "prompt_usage_ratio": 0.8,
        "threshold": 0.75,
    }
    assert compaction_events[1].payload == {
        "reason": "usage_threshold",
        "prompt_usage_ratio": 0.8,
        "threshold": 0.75,
        "mode": "summary_plus_recent",
    }


def test_agent_loop_compacts_and_retries_once_on_context_limit_error(tmp_path):
    knowledge_tools = QAKnowledgeToolHandlers(InMemoryQACardStore())
    dispatcher = create_dispatcher(tmp_path, knowledge_tools)
    events = []
    summarizer = FakeSummarizer(summary="retry summary")
    fake_llm = FakeLLM(
        [
            LLMContextLengthExceeded("context length exceeded"),
            LLMResponse(text="重试成功。"),
        ]
    )
    loop = AgentLoopRunner(
        llm=fake_llm,
        dispatcher=dispatcher,
        runtime_context_compactor=InMemoryRuntimeContextCompactor(
            summarizer=summarizer,
            recent_messages_count=1,
        ),
        event_sink=events.append,
    )

    answer = loop.run("触发超限")

    assert answer == "重试成功。"
    assert len(fake_llm.calls) == 2
    assert "retry summary" in fake_llm.calls[1]["system_prompt"]
    compaction_events = [
        event for event in events if event.event_type.startswith("runtime_context_compaction_")
    ]
    assert [event.event_type for event in compaction_events] == [
        "runtime_context_compaction_started",
        "runtime_context_compaction_finished",
    ]
    assert compaction_events[0].payload == {
        "reason": "context_length_exceeded",
        "prompt_usage_ratio": None,
        "threshold": 0.75,
    }
    assert compaction_events[1].payload == {
        "reason": "context_length_exceeded",
        "prompt_usage_ratio": None,
        "threshold": 0.75,
        "mode": "summary_plus_recent",
    }
