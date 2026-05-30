from personal_knowledge_agent.agent_loop import AgentLoop
from personal_knowledge_agent.schemas import LLMResponse, ToolCall
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
    )

    answer = loop.run("帮我记一条知识")

    assert answer == "已保存，来源是新建的 card_id。"
    assert len(fake_llm.calls) == 2
    second_messages = fake_llm.calls[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert "card_id" in second_messages[-1]["content"]


def test_agent_loop_returns_final_answer_without_tool_call(tmp_path):
    knowledge_tools = KnowledgeTools(SQLiteStore(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(knowledge_tools)
    fake_llm = FakeLLM([LLMResponse(text="本地知识库中没有找到足够依据。")])
    loop = AgentLoop(
        llm=fake_llm,
        tools=knowledge_tools,
        dispatcher=dispatcher,
    )

    assert loop.run("未知问题") == "本地知识库中没有找到足够依据。"
