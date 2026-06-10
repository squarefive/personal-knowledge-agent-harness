from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..agent_memory.document_store import MemoryStore
from ..agent_memory.index_store import MemoryIndexStore
from ..qa_store.sqlite_store import SQLiteStore
from ..qa_semantic_index import QASemanticIndex
from ..schemas import QACard

KEYWORD_SCORE_WEIGHT = 0.4
SEMANTIC_SCORE_WEIGHT = 0.6
STRONG_MATCH_THRESHOLD = 0.70
MEDIUM_MATCH_THRESHOLD = 0.50
WEAK_MATCH_THRESHOLD = 0.35


@dataclass
class HybridCandidate:
    card_id: str
    keyword_score: float = 0.0
    keyword_score_norm: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    match_level: str = "discard"
    matched_by: list[str] | None = None

    def add_match(self, source: str) -> None:
        if self.matched_by is None:
            self.matched_by = []
        if source not in self.matched_by:
            self.matched_by.append(source)


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
            message: str | None = None
            semantic_hits = []
            semantic_degraded = False
            if self.semantic_index is None or not self.semantic_index.is_enabled():
                warning = "语义检索未启用，已降级为本地关键词检索。"
                semantic_degraded = True
            else:
                try:
                    semantic_hits = self.semantic_index.search(query, limit=limit)
                except Exception as exc:
                    warning = f"语义检索失败，已降级为本地关键词检索: {exc}"
                    semantic_degraded = True

            candidates = self._rank_hybrid_candidates(
                keyword_scores={result.card_id: float(result.score) for result in keyword_results},
                semantic_scores={hit.card_id: hit.score for hit in semantic_hits},
                use_keyword_only_score=semantic_degraded,
            )
            returned_candidates = self._select_hybrid_candidates(candidates, limit=limit)
            if not semantic_degraded and not returned_candidates:
                message = "没有找到足够相关的本地知识卡片。"
            elif not semantic_degraded and returned_candidates[0].match_level == "weak":
                warning = "只找到弱相关候选，回答前应读取完整卡片并谨慎判断。"

            cards = self.store.read_cards_by_ids([candidate.card_id for candidate in returned_candidates])
            candidate_by_card_id = {candidate.card_id: candidate for candidate in returned_candidates}
            payload = {
                "ok": True,
                "cards": [
                    self._search_payload(card, candidate_by_card_id[card.id], rank=index + 1)
                    for index, card in enumerate(cards[:limit])
                ],
            }
            if warning:
                payload["warning"] = warning
            if message:
                payload["message"] = message
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
    def _search_payload(card: QACard, candidate: HybridCandidate, *, rank: int) -> dict[str, Any]:
        return {
            "rank": rank,
            "card_id": card.id,
            "question": card.question,
            "summary": card.summary,
            "answer_snippet": KnowledgeTools._snippet(card.answer),
            "score": candidate.final_score,
            "final_score": candidate.final_score,
            "match_level": candidate.match_level,
            "matched_by": candidate.matched_by or [],
            "keyword_score": candidate.keyword_score,
            "keyword_score_norm": candidate.keyword_score_norm,
            "semantic_score": candidate.semantic_score,
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

    def _rank_hybrid_candidates(
        self,
        *,
        keyword_scores: dict[str, float],
        semantic_scores: dict[str, float],
        use_keyword_only_score: bool,
    ) -> list[HybridCandidate]:
        candidates: dict[str, HybridCandidate] = {}
        for card_id, score in keyword_scores.items():
            candidate = candidates.setdefault(card_id, HybridCandidate(card_id=card_id))
            candidate.keyword_score = score
            candidate.add_match("keyword")
        for card_id, score in semantic_scores.items():
            candidate = candidates.setdefault(card_id, HybridCandidate(card_id=card_id))
            candidate.semantic_score = score
            candidate.add_match("semantic")

        max_keyword_score = max((candidate.keyword_score for candidate in candidates.values()), default=0.0)
        for candidate in candidates.values():
            candidate.keyword_score_norm = (
                candidate.keyword_score / max_keyword_score if max_keyword_score > 0 else 0.0
            )
            if use_keyword_only_score:
                candidate.final_score = candidate.keyword_score_norm
            else:
                candidate.final_score = (
                    KEYWORD_SCORE_WEIGHT * candidate.keyword_score_norm
                    + SEMANTIC_SCORE_WEIGHT * candidate.semantic_score
                )
            candidate.match_level = self._match_level(candidate.final_score)

        return sorted(candidates.values(), key=lambda item: item.final_score, reverse=True)

    @staticmethod
    def _select_hybrid_candidates(candidates: list[HybridCandidate], *, limit: int) -> list[HybridCandidate]:
        normal = [candidate for candidate in candidates if candidate.match_level in ("strong", "medium")]
        if normal:
            return normal[:limit]
        weak = [candidate for candidate in candidates if candidate.match_level == "weak"]
        return weak[:1]

    @staticmethod
    def _match_level(final_score: float) -> str:
        if final_score >= STRONG_MATCH_THRESHOLD:
            return "strong"
        if final_score >= MEDIUM_MATCH_THRESHOLD:
            return "medium"
        if final_score >= WEAK_MATCH_THRESHOLD:
            return "weak"
        return "discard"

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
