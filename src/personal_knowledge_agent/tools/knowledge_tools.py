from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..agent_memory.document_store import MemoryStore
from ..agent_memory.index_store import MemoryIndexStore
from ..qa_store.sqlite_store import SQLiteStore
from ..qa_semantic_index import QASemanticIndex
from ..schemas import QACard


class KnowledgeTools:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        memory_index_store: MemoryIndexStore | None = None,
        memory_store: MemoryStore | None = None,
        semantic_index: QASemanticIndex | None = None,
    ):
        self.store = store
        self.memory_index_store = memory_index_store
        self.memory_store = memory_store
        self.semantic_index = semantic_index

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
            result = {
                "ok": True,
                "card_id": card.id,
                "source_type": card.source_type,
                "created_at": card.created_at,
            }
            warning = self._try_upsert_semantic_index(card)
            if warning:
                result["warning"] = warning
            return result
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

    def hybrid_search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._required_text(arguments, "query")
            limit = self._optional_limit(arguments, default=5)
            keyword_results = self.store.search_cards(query, limit=limit)
            warning: str | None = None
            semantic_hits = []
            if self.semantic_index is None or not self.semantic_index.is_enabled():
                warning = "语义检索未启用，已降级为本地关键词检索。"
            else:
                try:
                    semantic_hits = self.semantic_index.search(query, limit=limit)
                except Exception as exc:
                    warning = f"语义检索失败，已降级为本地关键词检索: {exc}"

            card_ids = self._merge_card_ids(
                [result.card_id for result in keyword_results],
                [hit.card_id for hit in semantic_hits],
            )
            cards = self.store.read_cards_by_ids(card_ids)
            score_by_card_id: dict[str, float] = {
                result.card_id: float(result.score) for result in keyword_results
            }
            for hit in semantic_hits:
                score_by_card_id[hit.card_id] = score_by_card_id.get(hit.card_id, 0.0) + hit.score

            payload = {
                "ok": True,
                "cards": [
                    self._search_payload(card, score_by_card_id.get(card.id, 0.0))
                    for card in cards[:limit]
                ],
            }
            if warning:
                payload["warning"] = warning
            return payload
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

    def update_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_id = self._required_text(arguments, "card_id")
            patch = self._update_patch(arguments)
            card = self.store.update_card(card_id, **patch)
            if card is None:
                return self._error("not_found", f"card not found: {card_id}")
            result = {"ok": True, "card": self._card_payload(card)}
            warning = self._try_upsert_semantic_index(card)
            if warning:
                result["warning"] = warning
            return result
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def delete_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_id = self._required_text(arguments, "card_id")
            deleted = self.store.delete_card(card_id)
            if not deleted:
                return self._error("not_found", f"card not found: {card_id}")
            result = {"ok": True, "deleted_card_id": card_id}
            warning = self._try_delete_semantic_index(card_id)
            if warning:
                result["warning"] = warning
            return result
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def rebuild_qa_semantic_index(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = self._optional_limit(arguments, default=50) if "limit" in arguments else None
            if self.semantic_index is None or not self.semantic_index.is_enabled():
                return {
                    "ok": True,
                    "status": "disabled",
                    "message": "缺少 DASHSCOPE_API_KEY，无法向量化历史卡片。",
                    "total": 0,
                    "indexed": 0,
                    "failed": 0,
                    "failed_card_ids": [],
                }
            cards = self.store.list_unvectorized_cards(limit=limit)
            indexed = 0
            failed_card_ids: list[str] = []
            for card in cards:
                try:
                    self.semantic_index.upsert_card(card)
                    self.store.mark_card_vectorized(card.id)
                    indexed += 1
                except Exception:
                    failed_card_ids.append(card.id)
            return {
                "ok": True,
                "status": "ok" if not failed_card_ids else "partial_failed",
                "total": len(cards),
                "indexed": indexed,
                "failed": len(failed_card_ids),
                "failed_card_ids": failed_card_ids,
            }
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

    def _update_patch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        for name in ("question", "answer", "summary"):
            value = arguments.get(name)
            if value is not None:
                patch[name] = self._required_text(arguments, name)
        if "keywords" in arguments:
            patch["keywords"] = self._required_keywords(arguments)
        if not patch:
            raise ValueError("at least one field must be provided")
        return patch

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
    def _search_payload(card: QACard, score: float) -> dict[str, Any]:
        return {
            "card_id": card.id,
            "question": card.question,
            "summary": card.summary,
            "answer_snippet": KnowledgeTools._snippet(card.answer),
            "score": score,
            "source_type": card.source_type,
            "created_at": card.created_at,
        }

    def _try_upsert_semantic_index(self, card: QACard) -> str | None:
        if self.semantic_index is None or not self.semantic_index.is_enabled():
            return None
        try:
            self.semantic_index.upsert_card(card)
            self.store.mark_card_vectorized(card.id)
        except Exception as exc:
            return f"语义索引同步失败，可稍后执行 rebuild_qa_semantic_index 修复: {exc}"
        return None

    def _try_delete_semantic_index(self, card_id: str) -> str | None:
        if self.semantic_index is None or not self.semantic_index.is_enabled():
            return None
        try:
            self.semantic_index.delete_card(card_id)
        except Exception as exc:
            return f"语义索引删除失败，可稍后执行 rebuild_qa_semantic_index 修复: {exc}"
        return None

    @staticmethod
    def _merge_card_ids(keyword_card_ids: list[str], semantic_card_ids: list[str]) -> list[str]:
        merged: list[str] = []
        for card_id in [*keyword_card_ids, *semantic_card_ids]:
            if card_id not in merged:
                merged.append(card_id)
        return merged

    @staticmethod
    def _snippet(answer: str, length: int = 160) -> str:
        clean = " ".join(answer.split())
        if len(clean) <= length:
            return clean
        return f"{clean[: length - 3]}..."

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
            "description": "使用 SQLite LIKE 检索本地 Q&A 知识卡片，作为关键词检索和降级兜底。",
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
            "name": "hybrid_search_qa_cards",
            "description": "默认问答检索工具。结合 SQLite LIKE 和 Qdrant 语义召回检索本地 Q&A 知识卡片。",
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
            "name": "update_qa_card",
            "description": "更新一条本地 Q&A 知识卡片。该工具执行前必须经过 harness 权限确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_id": {"type": "string"},
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "summary": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["card_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_qa_card",
            "description": "物理删除一条本地 Q&A 知识卡片。该工具执行前必须经过 harness 权限确认。",
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
            "name": "rebuild_qa_semantic_index",
            "description": "把尚未向量化的历史 Q&A 卡片写入 Qdrant 本地语义索引。",
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
]
