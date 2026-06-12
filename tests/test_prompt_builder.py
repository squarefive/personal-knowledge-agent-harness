from personal_knowledge_agent.prompt_builder import build_system_prompt
from personal_knowledge_agent.schemas import (
    MemoryDocument,
    MemoryIndex,
    MemoryIndexEntry,
)


def test_build_system_prompt_keeps_base_rules():
    prompt = build_system_prompt()

    assert "你是一个本地个人 Q&A 知识库 Agent" in prompt
    assert "生成 summary、keywords 和 category" in prompt
    assert "keywords 是检索词；category 是这张卡片唯一的语义主归属分类" in prompt
    assert "不得使用“其他”“未分类”“杂项”“默认分类”“未知”“待分类”等兜底分类" in prompt
    assert "只有用户明确限定分类时" in prompt
    assert "用户未明确限定分类时，不要传 category" in prompt
    assert "如果要基于本地知识库回答，优先调用 hybrid_search_qa_cards" in prompt
    assert "hybrid_search_qa_cards 返回的是候选摘要，不是完整依据" in prompt
    assert "必须先调用 read_qa_card 读取该 card_id 的完整卡片" in prompt
    assert "通常应优先读取 rank=1 的候选" in prompt
    assert "如果只返回 weak 候选，读取完整卡片后仍要判断依据是否足够" in prompt
    assert "最终来源区块由程序根据工具结果生成" in prompt
    assert "高风险工具执行前由 harness 权限层请求用户确认" in prompt
    assert "permission_denied" in prompt
    assert "Q&A 知识库和 Agent memory 必须分开" in prompt


def test_build_system_prompt_injects_memory_index():
    prompt = build_system_prompt(
        memory_index=MemoryIndex(
            entries=[
                MemoryIndexEntry(
                    name="project-boundary",
                    type="project",
                    description="Project boundary",
                    path=".memory/project-boundary.md",
                )
            ]
        )
    )

    assert "可用 Agent memory 索引" in prompt
    assert "project-boundary (project): Project boundary [.memory/project-boundary.md]" in prompt


def test_build_system_prompt_injects_selected_memories():
    prompt = build_system_prompt(
        selected_memories=[
            MemoryDocument(
                name="project-boundary",
                type="project",
                description="Project boundary",
                path=".memory/project-boundary.md",
                updated_at="2026-05-31",
                source_type="user_decision",
                source_ref=None,
                content="Q&A 和 Agent memory 分开。",
            )
        ]
    )

    assert "本轮已加载的相关 Agent memory" in prompt
    assert "content: Q&A 和 Agent memory 分开。" in prompt
