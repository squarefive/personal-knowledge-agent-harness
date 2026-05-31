from personal_knowledge_agent.agent_memory import MemoryExtractor
from personal_knowledge_agent.schemas import MemoryIndex, MemoryIndexEntry


def test_extract_user_preference_requires_confirmation():
    candidates = MemoryExtractor().extract(
        user_input="记住：以后回答我先给结论。",
        final_answer="好的。",
    )

    assert len(candidates) == 1
    assert candidates[0].type == "user"
    assert candidates[0].source_type == "user_explicit"
    assert candidates[0].write_policy == "needs_confirmation"


def test_extract_project_decision_can_auto_write():
    candidates = MemoryExtractor().extract(
        user_input="我们决定：Q&A 知识库和 Agent memory 必须分开。",
        final_answer="已记录为设计决策。",
        recent_messages=[{"role": "user", "content": "当前在设计 Agent memory 管理"}],
    )

    assert len(candidates) == 1
    assert candidates[0].type == "project"
    assert candidates[0].source_type == "user_decision"
    assert candidates[0].write_policy == "auto_write"


def test_extract_ignores_temporary_smalltalk():
    candidates = MemoryExtractor().extract(
        user_input="今天先聊到这里。",
        final_answer="好的。",
    )

    assert candidates == []


def test_extract_dedupes_existing_memory_names():
    extractor = MemoryExtractor()
    candidates = extractor.extract(
        user_input="记住：以后回答我先给结论。",
        final_answer="好的。",
    )
    existing = MemoryIndex(
        entries=[
            MemoryIndexEntry(
                name=candidates[0].name,
                type="user",
                description="existing",
                path=".memory/existing.md",
            )
        ]
    )

    deduped = extractor.extract(
        user_input="记住：以后回答我先给结论。",
        final_answer="好的。",
        memory_index=existing,
    )

    assert deduped == []
