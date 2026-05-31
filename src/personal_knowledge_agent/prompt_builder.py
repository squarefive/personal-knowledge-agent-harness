from __future__ import annotations

from .schemas import MemoryDocument, MemoryIndex


def build_system_prompt(
    *,
    memory_index: MemoryIndex | None = None,
    selected_memories: list[MemoryDocument] | None = None,
) -> str:
    sections = [
        "\n".join(
            [
                "你是一个本地个人 Q&A 知识库 Agent。",
                "你的任务是把用户提供的 Q&A 保存为本地知识卡片，并在用户提问时先检索本地知识库。",
                "当用户要记录知识时，保留原始 question 和 answer，生成 summary 和 keywords，然后调用 save_qa_card。",
                "当用户提问时，必须先调用 search_qa_cards；必要时再调用 read_qa_card 核对完整来源。",
                "回答必须基于工具返回的本地知识卡片，并标注 card_id、原始问题、source_type 和 created_at。",
                "如果本地知识库没有足够依据，明确说明无法从本地知识库回答，不要编造。",
                "不要声称已经保存、查询或更新任何未通过工具完成的数据。",
                "Q&A 知识库和 Agent memory 必须分开；.memory 内容不能作为 Q&A 卡片来源。",
                "第一版不做 Wiki、文件监听、周报、多 Agent、向量数据库、去重合并或后台任务。",
            ]
        )
    ]
    if memory_index is not None:
        sections.append(_render_memory_index(memory_index))
    if selected_memories:
        sections.append(_render_selected_memories(selected_memories))
    return "\n\n".join(section for section in sections if section.strip())


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
