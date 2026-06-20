from personal_knowledge_agent.agent_context import build_system_prompt
from personal_knowledge_agent.agent_context.agent_profile_memory import (
    MemoryDocument,
    MemoryIndex,
    MemoryIndexEntry,
)


def test_build_system_prompt_keeps_base_rules():
    prompt = build_system_prompt()

    assert "# 角色" in prompt
    assert "# 知识录入" in prompt
    assert "# 分类规则" in prompt
    assert "# 检索与回答" in prompt
    assert "# category 过滤" in prompt
    assert "# 来源与证据" in prompt
    assert "# 更新与删除" in prompt
    assert "# 记忆边界" in prompt
    assert "你是一个本地个人 Q&A 知识库 Agent" in prompt
    assert "生成 summary、keywords 和 category" in prompt
    assert "如果用户没有提供明确 question/answer 或没有表达保存意图" in prompt
    assert "keywords 是检索词；category 是这张卡片唯一的语义主归属分类" in prompt
    assert "不超过 24 个字符" in prompt
    assert "不得使用“其他”“未分类”“杂项”“默认分类”“未知”“待分类”等兜底分类" in prompt
    assert "只有用户明确限定分类时" in prompt
    assert "用户未明确限定分类时，不要传 category" in prompt
    assert "当用户要求基于本地知识库、历史记录、已保存 Q&A 或来源回答时" in prompt
    assert "优先调用 hybrid_search_qa_cards" in prompt
    assert "hybrid_search_qa_cards 返回的是候选摘要，不是完整依据" in prompt
    assert "必须先调用 read_qa_card 读取该 card_id 的完整卡片" in prompt
    assert "通常先读取 rank=1 的候选" in prompt
    assert "应继续读取其他相关候选" in prompt
    assert "如果只返回 weak 候选，读取完整卡片后仍要判断依据是否足够" in prompt
    assert "先调用 detect_duplicate_cards(mode=manual)" in prompt
    assert "detect_duplicate_cards(mode=auto)" in prompt
    assert "真正合并必须调用 merge_qa_cards" in prompt
    assert "最终回答不要自行输出“来源：”区块" in prompt
    assert "来源区块由程序根据工具结果追加" in prompt
    assert "只有用户明确要求修改、删除或合并卡片时" in prompt
    assert "高风险工具执行前由 harness 权限层请求用户确认" in prompt
    assert "permission_denied" in prompt
    assert "Q&A 知识库和 Agent memory 必须分开" in prompt
    assert ".memory 内容只用于理解用户偏好、项目约束和协作上下文" in prompt


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


def test_build_system_prompt_injects_runtime_session_context():
    prompt = build_system_prompt(
        session_summary="\n".join(
            [
                "# Session Summary",
                "",
                "## Current Goal",
                "继续实现上下文压缩。",
                "",
                "## Boundaries",
                "summary 不是用户新请求，不是长期 memory，不是 Q&A 知识来源。",
            ]
        )
    )

    assert "# Runtime Session Context" in prompt
    assert "不是用户新请求，不是长期 memory，不是 Q&A 知识来源" in prompt
    assert "继续实现上下文压缩。" in prompt
