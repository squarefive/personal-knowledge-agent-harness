from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .memory_index import MemoryIndexStore
from .memory_store import MemoryStore
from .schemas import QACard, SearchResult, SessionSummary
from .session_store import SessionStore
from .sqlite_store import SQLiteStore


class KnowledgeTools:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        memory_index_store: MemoryIndexStore | None = None,
        memory_store: MemoryStore | None = None,
        session_store: SessionStore | None = None,
    ):
        self.store = store
        self.memory_index_store = memory_index_store
        self.memory_store = memory_store
        self.session_store = session_store

    def save_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            question = self._required_text(arguments, "question")
            answer = self._required_text(arguments, "answer")
            summary = self._required_text(arguments, "summary")
            keywords = self._required_keywords(arguments)
            card = self.store.save_card(
                question=question,
                answer=answer,
                summary=summary,
                keywords=keywords,
            )
            return {
                "ok": True,
                "card_id": card.id,
                "source_type": card.source_type,
                "created_at": card.created_at,
            }
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._required_text(arguments, "query")
            limit = self._optional_limit(arguments, default=5)
            cards = self.store.search_cards(query, limit=limit)
            return {"ok": True, "cards": [asdict(card) for card in cards]}
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def read_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_id = self._required_text(arguments, "card_id")
            card = self.store.read_card(card_id)
            if card is None:
                return self._error("not_found", f"card not found: {card_id}")
            return {"ok": True, "card": self._card_payload(card)}
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def list_recent_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = self._optional_limit(arguments, default=10)
            cards = self.store.list_recent_cards(limit=limit)
            return {"ok": True, "cards": [self._recent_payload(card) for card in cards]}
        except Exception as exc:
            return self._error("store_error", str(exc))

    def list_memory_index(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.memory_index_store is None:
            return self._error("memory_not_configured", "memory index store is not configured")
        try:
            limit = self._optional_limit(arguments, default=50)
            index = self.memory_index_store.load()
            return {"ok": True, "entries": [asdict(entry) for entry in index.entries[:limit]]}
        except Exception as exc:
            return self._error("invalid_memory_index", str(exc))

    def read_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.memory_index_store is None or self.memory_store is None:
            return self._error("memory_not_configured", "memory store is not configured")
        try:
            name = self._required_text(arguments, "name")
            index = self.memory_index_store.load()
            entry = next((item for item in index.entries if item.name == name), None)
            if entry is None:
                return self._error("not_found", f"memory not found: {name}")
            memory = self.memory_store.read_by_entry(entry)
            return {"ok": True, "memory": asdict(memory)}
        except Exception as exc:
            return self._error("invalid_memory", str(exc))

    def update_session_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.session_store is None:
            return self._error("session_not_configured", "session store is not configured")
        try:
            summary = SessionSummary(
                current_goal=self._optional_text(arguments, "current_goal"),
                confirmed_decisions=self._optional_string_list(arguments, "confirmed_decisions"),
                open_questions=self._optional_string_list(arguments, "open_questions"),
                next_steps=self._optional_string_list(arguments, "next_steps"),
            )
            path = self.session_store.write_current(summary)
            return {
                "ok": True,
                "path": str(path.relative_to(self.session_store.root)),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return self._error("session_write_failed", str(exc))

    def definitions(self) -> list[dict[str, Any]]:
        return TOOL_DEFINITIONS

    @staticmethod
    def _required_text(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _required_keywords(arguments: dict[str, Any]) -> list[str]:
        value = arguments.get("keywords")
        if not isinstance(value, list):
            raise ValueError("keywords must be a list of strings")
        keywords = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not keywords:
            raise ValueError("keywords must contain at least one non-empty string")
        return keywords

    @staticmethod
    def _optional_limit(arguments: dict[str, Any], default: int) -> int:
        value = arguments.get("limit", default)
        if not isinstance(value, int) or value < 1:
            return default
        return min(value, 50)

    @staticmethod
    def _optional_text(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value.strip()

    @staticmethod
    def _optional_string_list(arguments: dict[str, Any], name: str) -> list[str]:
        value = arguments.get(name, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"{name} must be a list of strings")
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @staticmethod
    def _card_payload(card: QACard) -> dict[str, Any]:
        return {
            "card_id": card.id,
            "question": card.question,
            "answer": card.answer,
            "summary": card.summary,
            "keywords": card.keywords,
            "source_type": card.source_type,
            "created_at": card.created_at,
            "updated_at": card.updated_at,
        }

    @staticmethod
    def _recent_payload(card: QACard) -> dict[str, Any]:
        return {
            "card_id": card.id,
            "question": card.question,
            "summary": card.summary,
            "keywords": card.keywords,
            "source_type": card.source_type,
            "created_at": card.created_at,
        }

    @staticmethod
    def _error(error_code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error_code": error_code, "message": message}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_qa_card",
            "description": "保存一条本地 Q&A 知识卡片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "summary": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question", "answer", "summary", "keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_qa_cards",
            "description": "检索本地 Q&A 知识卡片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_qa_card",
            "description": "按 card_id 读取完整 Q&A 知识卡片。",
            "parameters": {
                "type": "object",
                "properties": {"card_id": {"type": "string"}},
                "required": ["card_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_cards",
            "description": "列出最近保存的 Q&A 知识卡片。",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memory_index",
            "description": "列出 Agent memory 索引。",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "按 memory name 读取 Agent memory 全文。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_session_memory",
            "description": "更新当前 session memory。",
            "parameters": {
                "type": "object",
                "properties": {
                    "current_goal": {"type": "string"},
                    "confirmed_decisions": {"type": "array", "items": {"type": "string"}},
                    "open_questions": {"type": "array", "items": {"type": "string"}},
                    "next_steps": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
]
