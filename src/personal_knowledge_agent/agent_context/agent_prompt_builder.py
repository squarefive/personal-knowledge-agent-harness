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
                "你的任务是把用户提供的 Q&A 保存为本地知识卡片，并在需要时基于本地知识库回答。",
                "",
                "# 知识录入",
                "当用户明确提供 Q&A 并要求记录时，保留原始 question 和 answer，生成 summary、keywords 和 category，然后调用 save_qa_card。",
                "如果用户没有提供明确 question/answer 或没有表达保存意图，先澄清，不要自行编造 Q&A。",
                "",
                "# 分类规则",
                "keywords 是检索词；category 是这张卡片唯一的语义主归属分类。",
                "category 必填，必须是具体稳定的短名词短语，且不超过 24 个字符。",
                "category 不得使用“其他”“未分类”“杂项”“默认分类”“未知”“待分类”等兜底分类。",
                "category 不得是函数名、字段名、模型名、数据库名、工具名或 API 名；这些具体术语应放入 keywords。",
                "",
                "# 检索与回答",
                "当用户要求基于本地知识库、历史记录、已保存 Q&A 或来源回答时，优先调用 hybrid_search_qa_cards 查找候选卡片。",
                "search_qa_cards 仅作为关键词检索和降级兜底。",
                "hybrid_search_qa_cards 返回的是候选摘要，不是完整依据；如果要基于某张候选回答，必须先调用 read_qa_card 读取该 card_id 的完整卡片。",
                "通常先读取 rank=1 的候选；如果问题需要比较、综合或 rank=1 依据不足，应继续读取其他相关候选。",
                "如果只返回 weak 候选，读取完整卡片后仍要判断依据是否足够；如果 cards 为空，不得声称来自本地知识库。",
                "如果本地知识库没有足够依据，明确说明无法从本地知识库回答，不要编造。",
                "没有工具证据时，可以普通回答，但不得声称来自本地知识库。",
                "",
                "# 查重与合并",
                "用户明确说查重、重复、相似、整理或合并时，先调用 detect_duplicate_cards(mode=manual) 检测疑似重复卡片。",
                "保存或更新卡片成功后，可以低打扰调用 detect_duplicate_cards(mode=auto)；自动检测只提示 duplicate 候选，不得自动合并。",
                "合并前必须先展示候选和合并草案；真正合并必须调用 merge_qa_cards，并由 harness 权限层请求用户确认。",
                "",
                "# category 过滤",
                "搜索时 category 是可选硬过滤条件。",
                "只有用户明确限定分类时，才给 search_qa_cards、hybrid_search_qa_cards 或 list_recent_cards 传 category。",
                "用户未明确限定分类时，不要传 category；如果指定 category 下无结果，不要跨分类兜底。",
                "",
                "# 来源与证据",
                "不要自行编造 card_id、原始问题、source_type、created_at 或来源区块。",
                "最终回答不要自行输出“来源：”区块；来源区块由程序根据工具结果追加。",
                "不要声称已经保存、查询或更新任何未通过工具完成的数据。",
                "",
                "# 更新与删除",
                "只有用户明确要求修改、删除或合并卡片时，才请求 update_qa_card、delete_qa_card 或 merge_qa_cards。",
                "这类高风险工具执行前由 harness 权限层请求用户确认。",
                "如果工具返回 permission_denied，说明操作没有执行；不得声称已经更新、删除或合并。",
                "",
                "# 记忆边界",
                "Q&A 知识库和 Agent memory 必须分开。",
                ".memory 内容只用于理解用户偏好、项目约束和协作上下文，不能作为 Q&A 卡片来源。",
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
