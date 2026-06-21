from personal_knowledge_agent.agent_context import build_system_prompt
from personal_knowledge_agent.agent_context.agent_profile_memory import (
    MemoryDocument,
    MemoryIndex,
    MemoryIndexEntry,
)


def test_build_system_prompt_keeps_base_rules():
    prompt = build_system_prompt()

    assert "# 角色" in prompt
    assert "# 通用行为规则" in prompt
    assert "# 知识录入规则" in prompt
    assert "# 检索与回答规则" in prompt
    assert "# 来源与证据" in prompt
    assert "# 写操作与权限" in prompt
    assert "# 记忆边界" in prompt
    assert "# 能力边界" in prompt
    assert "你是一个本地个人 Q&A 知识库 Agent" in prompt
    assert "选择工具和构造参数时，以 tools 中的 name、description、parameters 和 required 字段为准" in prompt
    assert "不得把模型推测、外部知识或未确认内容伪装成用户提供的 Q&A" in prompt
    assert "当用户要求基于本地知识库、已保存 Q&A、历史记录或来源回答时" in prompt
    assert "必须取得足以支撑回答的完整工具证据" in prompt
    assert "scope=all" not in prompt
    assert "hybrid_search_qa_cards" not in prompt
    assert "read_qa_card" not in prompt
    assert "detect_duplicate_cards(mode=manual)" not in prompt
    assert "detect_duplicate_cards(mode=auto)" not in prompt
    assert "merge_qa_cards" not in prompt
    assert "最终回答不要自行输出“来源：”区块" in prompt
    assert "来源区块由程序根据工具结果追加" in prompt
    assert "只有用户明确要求修改、删除或合并卡片时" in prompt
    assert "有副作用或高风险工具执行前由 harness 权限层处理确认" in prompt
    assert "permission_denied" in prompt
    assert "Q&A 知识库和 Agent memory 必须分开" in prompt
    assert "Agent memory 只用于理解用户偏好、项目约束和协作上下文" in prompt


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
