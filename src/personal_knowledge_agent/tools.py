from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from .schemas import QACard, SearchResult
from .sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


class KnowledgeTools:
    def __init__(self, store: SQLiteStore):
        self.store = store

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
            logger.info("save_qa_card.success", extra={"card_id": card.id})
            return {
                "ok": True,
                "card_id": card.id,
                "source_type": card.source_type,
                "created_at": card.created_at,
            }
        except Exception as exc:
            logger.exception("save_qa_card.error")
            return self._error("invalid_input", str(exc))

    def search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._required_text(arguments, "query")
            limit = self._optional_limit(arguments, default=5)
            cards = self.store.search_cards(query, limit=limit)
            logger.info("search_qa_cards.success", extra={"count": len(cards)})
            return {"ok": True, "cards": [asdict(card) for card in cards]}
        except Exception as exc:
            logger.exception("search_qa_cards.error")
            return self._error("invalid_input", str(exc))

    def read_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_id = self._required_text(arguments, "card_id")
            card = self.store.read_card(card_id)
            if card is None:
                logger.info("read_qa_card.not_found", extra={"card_id": card_id})
                return self._error("not_found", f"card not found: {card_id}")
            logger.info("read_qa_card.success", extra={"card_id": card.id})
            return {"ok": True, "card": self._card_payload(card)}
        except Exception as exc:
            logger.exception("read_qa_card.error")
            return self._error("invalid_input", str(exc))

    def list_recent_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = self._optional_limit(arguments, default=10)
            cards = self.store.list_recent_cards(limit=limit)
            logger.info("list_recent_cards.success", extra={"count": len(cards)})
            return {"ok": True, "cards": [self._recent_payload(card) for card in cards]}
        except Exception as exc:
            logger.exception("list_recent_cards.error")
            return self._error("store_error", str(exc))

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
]
