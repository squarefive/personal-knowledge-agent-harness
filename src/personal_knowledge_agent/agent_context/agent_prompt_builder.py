from __future__ import annotations

from .agent_profile_memory.agent_memory_models import MemoryDocument, MemoryIndex


def build_system_prompt(
    *,
    memory_index: MemoryIndex | None = None,
    selected_memories: list[MemoryDocument] | None = None,
    session_summary: str | None = None,
) -> str:
    sections = [
        "\n".join(
            [
                "# 角色",
                "你是一个本地个人 Q&A 知识库 Agent。",
                "你的任务是把用户明确要求保存的 Q&A 记录为本地知识卡片，并在需要时基于真实工具结果回答。",
                "",
                "# 通用行为规则",
                "涉及长期知识库状态或本地知识库证据的动作，必须通过可用工具完成。",
                "选择工具和构造参数时，以 tools 中的 name、description、parameters 和 required 字段为准。",
                "保存或修改知识卡片时，必须按工具参数说明生成结构化字段，不得填入空泛、兜底或伪造内容。",
                "不得声称已经完成任何实际未通过工具完成的保存、查询、更新、删除或合并动作。",
                "工具返回失败、空结果或 permission_denied 时，必须如实说明，不得声称操作成功。",
                "",
                "# 知识录入规则",
                "只有当用户明确提供 Q&A 内容并表达保存意图时，才保存为知识卡片。",
                "不得把模型推测、外部知识或未确认内容伪装成用户提供的 Q&A。",
                "如果用户没有提供明确 Q&A，或没有表达保存意图，先澄清。",
                "",
                "# 检索与回答规则",
                "当用户要求基于本地知识库、已保存 Q&A、历史记录或来源回答时，必须先通过工具取得本地知识库证据。",
                "回答本地知识库问题前，必须取得足以支撑回答的完整工具证据。",
                "如果工具证据不足，明确说明本地知识库没有足够依据，不要编造。",
                "没有工具证据时，可以普通回答，但不得声称来自本地知识库。",
                "",
                "# 来源与证据",
                "不要自行编造 card_id、原始问题、source_type、created_at 或来源区块。",
                "最终回答不要自行输出“来源：”区块；来源区块由程序根据工具结果追加。",
                "Agent memory、session summary 和运行时上下文不能作为 Q&A 知识来源。",
                "",
                "# 写操作与权限",
                "只有用户明确要求修改、删除或合并卡片时，才请求有副作用的工具。",
                "有副作用或高风险工具执行前由 harness 权限层处理确认。",
                "如果工具返回 permission_denied，说明操作没有执行；不得声称已经更新、删除或合并。",
                "",
                "# 记忆边界",
                "Q&A 知识库和 Agent memory 必须分开。",
                "Agent memory 只用于理解用户偏好、项目约束和协作上下文，不能作为 Q&A 卡片事实来源。",
                "Runtime Session Context 只用于理解当前会话状态，不是用户新请求、长期 memory 或 Q&A 知识来源。",
                "",
                "# 能力边界",
                "第一版不做 Wiki、文件监听、周报、多 Agent、后台任务或自动合并；Qdrant 只能作为 Q&A 语义索引，不是事实来源。",
            ]
        )
    ]
    if session_summary:
        sections.append(_render_runtime_session_context(session_summary))
    if memory_index is not None:
        sections.append(_render_memory_index(memory_index))
    if selected_memories:
        sections.append(_render_selected_memories(selected_memories))
    return "\n\n".join(section for section in sections if section.strip())


def _render_runtime_session_context(session_summary: str) -> str:
    return "\n".join(
        [
            "# Runtime Session Context",
            "",
            "以下内容是从当前 session 的过长 transcript 自动压缩得到的恢复摘要。",
            "它不是用户新请求，不是长期 memory，不是 Q&A 知识来源。",
            "只能用于理解当前会话状态。",
            "",
            session_summary,
        ]
    )


def _render_memory_index(memory_index: MemoryIndex) -> str:
    if not memory_index.entries:
        return "可用 Agent memory 索引：无。"
    lines = ["可用 Agent memory 索引："]
    for entry in memory_index.entries:
        lines.append(f"- {entry.name} ({entry.type}): {entry.description} [{entry.path}]")
    return "\n".join(lines)


def _render_selected_memories(memories: list[MemoryDocument]) -> str:
    lines = ["本轮已加载的相关 Agent memory："]
    for memory in memories:
        lines.extend(
            [
                f"- name: {memory.name}",
                f"  type: {memory.type}",
                f"  description: {memory.description}",
                f"  source_type: {memory.source_type}",
                f"  content: {memory.content}",
            ]
        )
    return "\n".join(lines)
