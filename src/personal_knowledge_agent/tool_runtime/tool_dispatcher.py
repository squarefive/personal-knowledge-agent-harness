from __future__ import annotations

from typing import Any, Callable

from ..agent_tools.agent_memory_tools import AgentMemoryToolHandlers
from ..agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from .tool_models import ToolCall


class ToolDispatcher:
    def __init__(
        self,
        qa_tools: QAKnowledgeToolHandlers,
        memory_tools: AgentMemoryToolHandlers,
    ):
        self._definitions = [*qa_tools.definitions(), *memory_tools.definitions()]
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "save_qa_card": qa_tools.save_qa_card,
            "search_qa_cards": qa_tools.search_qa_cards,
            "hybrid_search_qa_cards": qa_tools.hybrid_search_qa_cards,
            "read_qa_card": qa_tools.read_qa_card,
            "update_qa_card": qa_tools.update_qa_card,
            "delete_qa_card": qa_tools.delete_qa_card,
            "list_recent_cards": qa_tools.list_recent_cards,
            "detect_duplicate_cards": qa_tools.detect_duplicate_cards,
            "merge_qa_cards": qa_tools.merge_qa_cards,
            "rebuild_qa_semantic_index": qa_tools.rebuild_qa_semantic_index,
            "list_memory_index": memory_tools.list_memory_index,
            "read_memory": memory_tools.read_memory,
        }

    def definitions(self) -> list[dict[str, Any]]:
        return self._definitions

    def execute(self, tool_call: ToolCall) -> dict[str, Any]:
        handler = self._handlers.get(tool_call.name)
        if handler is None:
            return {"ok": False, "error_code": "unknown_tool", "message": tool_call.name}
        try:
            return handler(tool_call.arguments)
        except Exception as exc:
            return {"ok": False, "error_code": "tool_error", "message": str(exc)}

    def display_input(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._select(arguments, DISPLAY_INPUT_FIELDS.get(tool_name, ()))

    def display_output(self, tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
        return self._select(result, DISPLAY_OUTPUT_FIELDS.get(tool_name, ERROR_OUTPUT_FIELDS))

    def _select(self, payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
        selected: dict[str, Any] = {}
        for field in fields:
            self._copy_field(payload, selected, field.split("."))
        return selected

    def _copy_field(self, source: Any, target: Any, parts: list[str]) -> None:
        if not parts:
            return
        head, *tail = parts
        if isinstance(source, list):
            if not isinstance(target, list):
                return
            while len(target) < len(source):
                target.append({})
            for index, item in enumerate(source):
                self._copy_field(item, target[index], parts)
            return
        if not isinstance(source, dict) or head not in source:
            return
        if not tail:
            if isinstance(target, dict):
                target[head] = source[head]
            return
        value = source[head]
        if isinstance(value, list):
            next_target = target.setdefault(head, []) if isinstance(target, dict) else []
        else:
            next_target = target.setdefault(head, {}) if isinstance(target, dict) else {}
        self._copy_field(value, next_target, tail)


DISPLAY_INPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "save_qa_card": ("question", "answer", "summary", "keywords", "category"),
    "search_qa_cards": ("query", "limit", "category"),
    "hybrid_search_qa_cards": ("query", "limit", "category"),
    "read_qa_card": ("card_id",),
    "update_qa_card": ("card_id", "question", "answer", "summary", "keywords", "category"),
    "delete_qa_card": ("card_id",),
    "list_recent_cards": ("limit", "category"),
    "detect_duplicate_cards": ("card_id", "query", "category", "limit", "mode"),
    "merge_qa_cards": ("card_ids", "question", "answer", "summary", "keywords", "category"),
    "rebuild_qa_semantic_index": ("limit",),
    "list_memory_index": ("limit",),
    "read_memory": ("name",),
}

ERROR_OUTPUT_FIELDS = ("ok", "error_code", "message")

DISPLAY_OUTPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "save_qa_card": ("ok", "card_id", "source_type", "created_at", "category", "error_code", "message"),
    "search_qa_cards": (
        "ok",
        "cards.card_id",
        "cards.question",
        "cards.summary",
        "cards.answer_snippet",
        "cards.score",
        "cards.source_type",
        "cards.created_at",
        "cards.category",
        "error_code",
        "message",
    ),
    "hybrid_search_qa_cards": (
        "ok",
        "cards.rank",
        "cards.card_id",
        "cards.question",
        "cards.summary",
        "cards.answer_snippet",
        "cards.score",
        "cards.final_score",
        "cards.match_level",
        "cards.matched_by",
        "cards.keyword_score",
        "cards.keyword_score_norm",
        "cards.semantic_score",
        "cards.source_type",
        "cards.created_at",
        "cards.category",
        "warning",
        "message",
        "error_code",
    ),
    "read_qa_card": (
        "ok",
        "card.card_id",
        "card.question",
        "card.answer",
        "card.summary",
        "card.keywords",
        "card.category",
        "card.source_type",
        "card.created_at",
        "card.updated_at",
        "error_code",
        "message",
    ),
    "update_qa_card": (
        "ok",
        "card.card_id",
        "card.question",
        "card.answer",
        "card.summary",
        "card.keywords",
        "card.category",
        "card.source_type",
        "card.created_at",
        "card.updated_at",
        "error_code",
        "message",
    ),
    "delete_qa_card": (
        "ok",
        "deleted_card_id",
        "error_code",
        "message",
    ),
    "list_recent_cards": (
        "ok",
        "cards.card_id",
        "cards.question",
        "cards.summary",
        "cards.keywords",
        "cards.category",
        "cards.source_type",
        "cards.created_at",
        "error_code",
        "message",
    ),
    "detect_duplicate_cards": (
        "ok",
        "checked_card_id",
        "candidates.card_id",
        "candidates.question",
        "candidates.summary",
        "candidates.category",
        "candidates.duplicate_score",
        "candidates.duplicate_level",
        "candidates.reason",
        "warning",
        "error_code",
        "message",
    ),
    "merge_qa_cards": (
        "ok",
        "new_card_id",
        "deleted_card_ids",
        "source_type",
        "created_at",
        "category",
        "warning",
        "error_code",
        "message",
    ),
    "rebuild_qa_semantic_index": (
        "ok",
        "status",
        "message",
        "total",
        "indexed",
        "failed",
        "failed_card_ids",
        "error_code",
        "message",
    ),
    "list_memory_index": (
        "ok",
        "entries.name",
        "entries.type",
        "entries.description",
        "entries.path",
        "error_code",
        "message",
    ),
    "read_memory": (
        "ok",
        "memory.name",
        "memory.type",
        "memory.description",
        "memory.path",
        "memory.updated_at",
        "memory.source_type",
        "memory.content",
        "error_code",
        "message",
    ),
}
