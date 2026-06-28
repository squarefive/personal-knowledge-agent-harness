from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from ...qa_data_access import QACard, SearchResult, SemanticSearchHit
from ...qa_data_access.duplicate_detection import DuplicateDetectionService, DuplicateGroup

KEYWORD_SCORE_WEIGHT = 0.4
SEMANTIC_SCORE_WEIGHT = 0.6
STRONG_MATCH_THRESHOLD = 0.70
MEDIUM_MATCH_THRESHOLD = 0.50
WEAK_MATCH_THRESHOLD = 0.35
DUPLICATE_SEMANTIC_WEIGHT = 0.55
DUPLICATE_KEYWORD_OVERLAP_WEIGHT = 0.25
DUPLICATE_QUESTION_OVERLAP_WEIGHT = 0.15
DUPLICATE_CATEGORY_WEIGHT = 0.05
DUPLICATE_SEMANTIC_THRESHOLD = 0.88
DUPLICATE_SCORE_THRESHOLD = 0.82
POSSIBLE_DUPLICATE_SCORE_THRESHOLD = 0.70
POSSIBLE_CROSS_CATEGORY_SEMANTIC_THRESHOLD = 0.93


class QACardStore(Protocol):
    def save_card(
        self,
        *,
        question: str,
        answer: str,
        summary: str,
        keywords: list[str],
        category: str,
    ) -> QACard: ...

    def search_cards(
        self,
        query: str,
        limit: int = 5,
        category: str | None = None,
    ) -> list[SearchResult]: ...

    def read_card(self, card_id: str) -> QACard | None: ...

    def update_card(
        self,
        card_id: str,
        *,
        question: str | None = None,
        answer: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        category: str | None = None,
    ) -> QACard | None: ...

    def delete_card(self, card_id: str) -> bool: ...

    def list_recent_cards(self, limit: int = 10, category: str | None = None) -> list[QACard]: ...

    def list_all_cards(self, category: str | None = None) -> list[QACard]: ...

    def list_unvectorized_cards(self, limit: int | None = None) -> list[QACard]: ...

    def read_cards_by_ids(self, card_ids: list[str], category: str | None = None) -> list[QACard]: ...

    def mark_card_vectorized(self, card_id: str) -> bool: ...

    def validate_category(self, category: str) -> str: ...


class QASemanticIndex(Protocol):
    def is_enabled(self) -> bool: ...

    def search(self, query: str, limit: int) -> list[SemanticSearchHit]: ...

    def upsert_card(self, card: QACard) -> None: ...

    def delete_card(self, card_id: str) -> None: ...


@dataclass
class QAKnowledgeSearchCandidate:
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


@dataclass
class DuplicateCandidate:
    card_id: str
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    keyword_score_norm: float = 0.0
    keyword_overlap: float = 0.0
    question_overlap: float = 0.0
    same_category: bool = False
    duplicate_score: float = 0.0
    duplicate_level: str = ""
    reason: str = ""


class QAKnowledgeToolHandlers:
    def __init__(
        self,
        store: QACardStore,
        *,
        semantic_index: QASemanticIndex | None = None,
    ):
        self.store = store
        self.semantic_index = semantic_index
        self.duplicate_detection = DuplicateDetectionService()

    def save_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            question = self._required_text(arguments, "question")
            answer = self._required_text(arguments, "answer")
            summary = self._required_text(arguments, "summary")
            keywords = self._required_keywords(arguments)
            category = self._required_text(arguments, "category")
            card = self.store.save_card(
                question=question,
                answer=answer,
                summary=summary,
                keywords=keywords,
                category=category,
            )
            result = {
                "ok": True,
                "card_id": card.id,
                "source_type": card.source_type,
                "created_at": card.created_at,
                "category": card.category,
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
            category = self._optional_category(arguments)
            cards = self.store.search_cards(query, limit=limit, category=category)
            return {"ok": True, "cards": [asdict(card) for card in cards]}
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def hybrid_search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._required_text(arguments, "query")
            limit = self._optional_limit(arguments, default=5)
            category = self._optional_category(arguments)
            keyword_results = self.store.search_cards(query, limit=limit, category=category)
            warning: str | None = None
            message: str | None = None
            semantic_hits = []
            semantic_degraded = False
            if self.semantic_index is None or not self.semantic_index.is_enabled():
                warning = "语义召回未启用，已降级为关键词检索。"
                semantic_degraded = True
            else:
                try:
                    semantic_limit = max(limit * 5, 20) if category is not None else limit
                    semantic_hits = self.semantic_index.search(query, limit=semantic_limit)
                except Exception as exc:
                    warning = f"语义检索失败，已降级为关键词检索: {exc}"
                    semantic_degraded = True

            candidates = self._rank_hybrid_candidates(
                keyword_scores={result.card_id: float(result.score) for result in keyword_results},
                semantic_scores={hit.card_id: hit.score for hit in semantic_hits},
                use_keyword_only_score=semantic_degraded,
            )
            if category is not None:
                allowed_cards = self.store.read_cards_by_ids(
                    [candidate.card_id for candidate in candidates],
                    category=category,
                )
                allowed_card_ids = {card.id for card in allowed_cards}
                candidates = [candidate for candidate in candidates if candidate.card_id in allowed_card_ids]
            returned_candidates = self._select_hybrid_candidates(candidates, limit=limit)
            if not semantic_degraded and not returned_candidates:
                message = (
                    "指定 category 下没有找到相关知识卡片。"
                    if category is not None
                    else "没有找到足够相关的知识卡片。"
                )
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
            category = self._optional_category(arguments)
            cards = self.store.list_recent_cards(limit=limit, category=category)
            return {"ok": True, "cards": [self._recent_payload(card) for card in cards]}
        except Exception as exc:
            return self._error("store_error", str(exc))

    def detect_duplicate_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Detect duplicate cards for a target card/query or the whole library.

        Inputs:
            arguments: Tool call arguments including scope, mode, and filters.
        Outputs:
            Structured tool result with candidates or duplicate groups.
        Side Effects:
            None.
        """
        try:
            limit = self._optional_limit(arguments, default=5)
            scope = self._duplicate_scope(arguments)
            mode = self._duplicate_mode(arguments)
            category = self._optional_category(arguments)
            if scope == "all":
                return self._detect_all_duplicate_cards(
                    category=category,
                    limit=limit,
                    mode=mode,
                )
            return self._detect_target_duplicate_cards(
                arguments=arguments,
                category=category,
                limit=limit,
                mode=mode,
            )
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def _detect_all_duplicate_cards(
        self,
        *,
        category: str | None,
        limit: int,
        mode: str,
    ) -> dict[str, Any]:
        """Return duplicate groups across all matching cards."""
        cards = self.store.list_all_cards(category=category)
        result = self.duplicate_detection.detect_all(cards, mode=mode, limit=limit)
        return {
            "ok": True,
            "scope": "all",
            "checked_count": result.checked_count,
            "duplicate_groups": [
                self._duplicate_group_payload(group)
                for group in result.duplicate_groups
            ],
        }

    def _detect_target_duplicate_cards(
        self,
        *,
        arguments: dict[str, Any],
        category: str | None,
        limit: int,
        mode: str,
    ) -> dict[str, Any]:
        """Return duplicate candidates for one target card or query."""
        try:
            target_card = self._optional_target_card(arguments)
            query = self._duplicate_query(arguments, target_card)
            checked_card_id = target_card.id if target_card is not None else None
            effective_category = category
            over_fetch_limit = max(limit * 5, 20)
            keyword_results = self.store.search_cards(query, limit=over_fetch_limit, category=effective_category)
            warning: str | None = None
            semantic_hits = []
            if self.semantic_index is None or not self.semantic_index.is_enabled():
                warning = "语义召回未启用，已降级为关键词查重。"
            else:
                try:
                    semantic_hits = self.semantic_index.search(query, limit=over_fetch_limit)
                except Exception as exc:
                    warning = f"语义检索失败，已降级为关键词查重: {exc}"

            candidates = self._rank_duplicate_candidates(
                target_card=target_card,
                keyword_scores={result.card_id: float(result.score) for result in keyword_results},
                semantic_scores={hit.card_id: hit.score for hit in semantic_hits},
                excluded_card_id=checked_card_id,
                category=effective_category,
            )
            if mode == "auto":
                candidates = [item for item in candidates if item[1].duplicate_level == "duplicate"]
            payload = {
                "ok": True,
                "scope": "target",
                "checked_card_id": checked_card_id,
                "candidates": [
                    self._duplicate_payload(card, candidate)
                    for card, candidate in candidates[:limit]
                ],
            }
            if warning:
                payload["warning"] = warning
            return payload
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def merge_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_ids = self._required_card_ids(arguments)
            original_cards = self.store.read_cards_by_ids(card_ids)
            found_card_ids = {card.id for card in original_cards}
            missing_card_ids = [card_id for card_id in card_ids if card_id not in found_card_ids]
            if missing_card_ids:
                return self._error("not_found", f"cards not found: {', '.join(missing_card_ids)}")

            question = self._required_text(arguments, "question")
            answer = self._required_text(arguments, "answer")
            summary = self._required_text(arguments, "summary")
            keywords = self._required_keywords(arguments)
            category = self._required_text(arguments, "category")
            new_card = self.store.save_card(
                question=question,
                answer=answer,
                summary=summary,
                keywords=keywords,
                category=category,
            )
            warnings: list[str] = []
            for card_id in card_ids:
                self.store.delete_card(card_id)
                warning = self._try_delete_semantic_index(card_id)
                if warning:
                    warnings.append(warning)
            warning = self._try_upsert_semantic_index(new_card)
            if warning:
                warnings.append(warning)
            result = {
                "ok": True,
                "new_card_id": new_card.id,
                "deleted_card_ids": card_ids,
                "source_type": new_card.source_type,
                "created_at": new_card.created_at,
                "category": new_card.category,
            }
            if warnings:
                result["warning"] = "；".join(warnings)
            return result
        except Exception as exc:
            return self._error("invalid_input", str(exc))

    def definitions(self) -> list[dict[str, Any]]:
        return QA_KNOWLEDGE_TOOL_DEFINITIONS

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

    def _optional_category(self, arguments: dict[str, Any]) -> str | None:
        if "category" not in arguments or arguments.get("category") is None:
            return None
        return self.store.validate_category(self._required_text(arguments, "category"))

    def _optional_target_card(self, arguments: dict[str, Any]) -> QACard | None:
        if "card_id" not in arguments or arguments.get("card_id") is None:
            return None
        card_id = self._required_text(arguments, "card_id")
        card = self.store.read_card(card_id)
        if card is None:
            raise ValueError(f"card not found: {card_id}")
        return card

    @staticmethod
    def _duplicate_scope(arguments: dict[str, Any]) -> str:
        """Return the validated duplicate detection scope."""
        scope = arguments.get("scope", "target")
        if scope not in ("target", "all"):
            raise ValueError("scope must be target or all")
        return scope

    @staticmethod
    def _duplicate_mode(arguments: dict[str, Any]) -> str:
        mode = arguments.get("mode", "manual")
        if mode not in ("manual", "auto"):
            raise ValueError("mode must be manual or auto")
        return mode

    def _duplicate_query(self, arguments: dict[str, Any], target_card: QACard | None) -> str:
        query = arguments.get("query")
        if isinstance(query, str) and query.strip():
            return query.strip()
        if target_card is not None:
            return " ".join([target_card.question, target_card.summary, *target_card.keywords, target_card.category])
        raise ValueError("card_id or query must be provided")

    @staticmethod
    def _required_card_ids(arguments: dict[str, Any]) -> list[str]:
        value = arguments.get("card_ids")
        if not isinstance(value, list):
            raise ValueError("card_ids must be a list of strings")
        card_ids: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip() and item.strip() not in card_ids:
                card_ids.append(item.strip())
        if len(card_ids) < 2:
            raise ValueError("card_ids must contain at least two unique card ids")
        return card_ids

    def _update_patch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        for name in ("question", "answer", "summary"):
            value = arguments.get(name)
            if value is not None:
                patch[name] = self._required_text(arguments, name)
        if "keywords" in arguments:
            patch["keywords"] = self._required_keywords(arguments)
        if "category" in arguments:
            patch["category"] = self._required_text(arguments, "category")
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
            "category": card.category,
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
            "category": card.category,
            "source_type": card.source_type,
            "created_at": card.created_at,
        }

    @staticmethod
    def _search_payload(
        card: QACard,
        candidate: QAKnowledgeSearchCandidate,
        *,
        rank: int,
    ) -> dict[str, Any]:
        return {
            "rank": rank,
            "card_id": card.id,
            "question": card.question,
            "summary": card.summary,
            "answer_snippet": QAKnowledgeToolHandlers._snippet(card.answer),
            "score": candidate.final_score,
            "final_score": candidate.final_score,
            "match_level": candidate.match_level,
            "matched_by": candidate.matched_by or [],
            "keyword_score": candidate.keyword_score,
            "keyword_score_norm": candidate.keyword_score_norm,
            "semantic_score": candidate.semantic_score,
            "source_type": card.source_type,
            "created_at": card.created_at,
            "category": card.category,
        }

    @staticmethod
    def _duplicate_payload(card: QACard, candidate: DuplicateCandidate) -> dict[str, Any]:
        return {
            "card_id": card.id,
            "question": card.question,
            "summary": card.summary,
            "category": card.category,
            "duplicate_score": candidate.duplicate_score,
            "duplicate_level": candidate.duplicate_level,
            "semantic_score": candidate.semantic_score,
            "keyword_score_norm": candidate.keyword_score_norm,
            "keyword_overlap": candidate.keyword_overlap,
            "question_overlap": candidate.question_overlap,
            "same_category": candidate.same_category,
            "reason": candidate.reason,
        }

    @staticmethod
    def _duplicate_group_payload(group: DuplicateGroup) -> dict[str, Any]:
        """Return the tool payload for one duplicate group."""
        return {
            "card_ids": group.card_ids,
            "duplicate_score": group.duplicate_score,
            "duplicate_level": group.duplicate_level,
            "reason": group.reason,
            "cards": [
                {
                    "card_id": card.id,
                    "question": card.question,
                    "summary": card.summary,
                    "category": card.category,
                }
                for card in group.cards
            ],
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
    ) -> list[QAKnowledgeSearchCandidate]:
        candidates: dict[str, QAKnowledgeSearchCandidate] = {}
        for card_id, score in keyword_scores.items():
            candidate = candidates.setdefault(card_id, QAKnowledgeSearchCandidate(card_id=card_id))
            candidate.keyword_score = score
            candidate.add_match("keyword")
        for card_id, score in semantic_scores.items():
            candidate = candidates.setdefault(card_id, QAKnowledgeSearchCandidate(card_id=card_id))
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

    def _rank_duplicate_candidates(
        self,
        *,
        target_card: QACard | None,
        keyword_scores: dict[str, float],
        semantic_scores: dict[str, float],
        excluded_card_id: str | None,
        category: str | None,
    ) -> list[tuple[QACard, DuplicateCandidate]]:
        candidates: dict[str, DuplicateCandidate] = {}
        for card_id, score in keyword_scores.items():
            if card_id == excluded_card_id:
                continue
            candidates.setdefault(card_id, DuplicateCandidate(card_id=card_id)).keyword_score = score
        for card_id, score in semantic_scores.items():
            if card_id == excluded_card_id:
                continue
            candidates.setdefault(card_id, DuplicateCandidate(card_id=card_id)).semantic_score = score

        max_keyword_score = max((candidate.keyword_score for candidate in candidates.values()), default=0.0)
        cards = self.store.read_cards_by_ids(list(candidates), category=category)
        ranked: list[tuple[QACard, DuplicateCandidate]] = []
        for card in cards:
            candidate = candidates[card.id]
            candidate.keyword_score_norm = (
                candidate.keyword_score / max_keyword_score if max_keyword_score > 0 else 0.0
            )
            candidate.same_category = target_card is not None and card.category == target_card.category
            candidate.keyword_overlap = self._keyword_overlap(target_card, card)
            candidate.question_overlap = self._text_overlap(
                target_card.question if target_card is not None else "",
                card.question,
            )
            candidate.duplicate_score = self._duplicate_score(candidate)
            candidate.duplicate_level = self._duplicate_level(candidate)
            if candidate.duplicate_level:
                candidate.reason = self._duplicate_reason(candidate)
                ranked.append((card, candidate))
        return sorted(ranked, key=lambda item: item[1].duplicate_score, reverse=True)

    @staticmethod
    def _duplicate_score(candidate: DuplicateCandidate) -> float:
        category_bonus = 1.0 if candidate.same_category else 0.0
        score = (
            DUPLICATE_SEMANTIC_WEIGHT * candidate.semantic_score
            + DUPLICATE_KEYWORD_OVERLAP_WEIGHT * candidate.keyword_overlap
            + DUPLICATE_QUESTION_OVERLAP_WEIGHT * candidate.question_overlap
            + DUPLICATE_CATEGORY_WEIGHT * category_bonus
        )
        return round(score, 3)

    @staticmethod
    def _duplicate_level(candidate: DuplicateCandidate) -> str:
        if candidate.same_category and (
            candidate.semantic_score >= DUPLICATE_SEMANTIC_THRESHOLD
            or candidate.duplicate_score >= DUPLICATE_SCORE_THRESHOLD
        ):
            return "duplicate"
        if candidate.same_category and candidate.duplicate_score >= POSSIBLE_DUPLICATE_SCORE_THRESHOLD:
            return "possible_duplicate"
        if candidate.same_category and candidate.keyword_score_norm >= 0.85 and candidate.keyword_overlap >= 0.5:
            return "possible_duplicate"
        if not candidate.same_category and candidate.semantic_score >= POSSIBLE_CROSS_CATEGORY_SEMANTIC_THRESHOLD:
            return "possible_duplicate"
        return ""

    @staticmethod
    def _duplicate_reason(candidate: DuplicateCandidate) -> str:
        parts = []
        if candidate.same_category:
            parts.append("同分类")
        if candidate.semantic_score:
            parts.append("语义相似")
        if candidate.keyword_overlap:
            parts.append("关键词重合")
        if candidate.question_overlap:
            parts.append("问题文本相似")
        return "，".join(parts) if parts else "相似度达到查重阈值"

    @staticmethod
    def _keyword_overlap(target_card: QACard | None, candidate_card: QACard) -> float:
        if target_card is None:
            return 0.0
        target_keywords = {keyword.lower() for keyword in target_card.keywords}
        candidate_keywords = {keyword.lower() for keyword in candidate_card.keywords}
        if not target_keywords or not candidate_keywords:
            return 0.0
        return round(len(target_keywords & candidate_keywords) / max(len(target_keywords), len(candidate_keywords)), 3)

    @classmethod
    def _text_overlap(cls, left: str, right: str) -> float:
        left_terms = cls._text_terms(left)
        right_terms = cls._text_terms(right)
        if not left_terms or not right_terms:
            return 0.0
        return round(len(left_terms & right_terms) / max(len(left_terms), len(right_terms)), 3)

    @staticmethod
    def _text_terms(text: str) -> set[str]:
        clean = text.lower().strip()
        terms = {part for part in clean.split() if part}
        terms.update(character for character in clean if "\u4e00" <= character <= "\u9fff")
        return terms

    @staticmethod
    def _select_hybrid_candidates(
        candidates: list[QAKnowledgeSearchCandidate],
        *,
        limit: int,
    ) -> list[QAKnowledgeSearchCandidate]:
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


QA_KNOWLEDGE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "save_qa_card",
            "description": "保存当前用户的一条 Q&A 知识卡片。仅在用户明确提供 Q&A 并表达保存意图时使用；本工具会写入服务端事实库，并在语义索引启用时同步 pgvector 向量索引。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用户提供的原始问题，不要改写为模型自造问题。",
                    },
                    "answer": {
                        "type": "string",
                        "description": "用户提供的原始答案，不要用模型外部知识补写。",
                    },
                    "summary": {
                        "type": "string",
                        "description": "对答案的简短摘要，用于快速浏览和检索。",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "检索关键词，包括主题词、技术名词、项目名、工具名、API 名、模型名、数据库名、函数名或关键概念。",
                    },
                    "category": {
                        "type": "string",
                        "description": "知识卡片唯一的语义主归属分类。必须是具体稳定的短名词短语，不超过 24 个字符；不得使用其他、未分类、杂项、默认分类、未知、待分类等兜底分类；不得使用函数名、字段名、模型名、数据库名、工具名或 API 名。",
                    },
                },
                "required": ["question", "answer", "summary", "keywords", "category"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_qa_cards",
            "description": "使用关键词检索当前用户的 Q&A 知识卡片，作为基础检索和降级兜底。返回候选摘要，不是完整回答依据；需要回答时继续读取完整卡片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户问题或检索关键词。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量，工具会限制到允许范围。",
                    },
                    "category": {
                        "type": "string",
                        "description": "可选硬过滤分类。只有用户明确限定分类时才传入；指定分类无结果时不要跨分类兜底。",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hybrid_search_qa_cards",
            "description": "默认 Q&A 检索工具。用于用户要求基于当前用户个人知识库、已保存 Q&A、历史记录或来源回答时；返回候选摘要和排序信息，不是完整回答依据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户问题或检索意图。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量，工具会限制到允许范围。",
                    },
                    "category": {
                        "type": "string",
                        "description": "可选硬过滤分类。只有用户明确限定分类时才传入；指定分类无结果时不要跨分类兜底。",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_qa_card",
            "description": "按 card_id 读取当前用户可访问的完整 Q&A 知识卡片。用于把检索、最近列表或保存结果中的真实 card_id 转换为完整回答依据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_id": {
                        "type": "string",
                        "description": "来自检索、最近列表或保存结果的真实 card_id。",
                    }
                },
                "required": ["card_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_qa_card",
            "description": "更新当前用户的一条 Q&A 知识卡片。仅当用户明确要求修改某张卡片时使用；本工具属于高风险写操作，执行前必须经过 harness 权限确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_id": {
                        "type": "string",
                        "description": "要更新的卡片 ID。",
                    },
                    "question": {
                        "type": "string",
                        "description": "新的问题文本，不得用模型自造问题覆盖用户真实意图。",
                    },
                    "answer": {
                        "type": "string",
                        "description": "新的答案文本，不得用模型外部知识补写。",
                    },
                    "summary": {
                        "type": "string",
                        "description": "新的摘要，用于快速浏览和检索。",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "新的检索关键词，包括主题词、技术名词、项目名、工具名、API 名、模型名、数据库名、函数名或关键概念。",
                    },
                    "category": {
                        "type": "string",
                        "description": "新的唯一语义主分类。必须是具体稳定的短名词短语，不超过 24 个字符；不得使用兜底分类；不得使用函数名、字段名、模型名、数据库名、工具名或 API 名。",
                    },
                },
                "required": ["card_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_qa_card",
            "description": "物理删除当前用户的一条 Q&A 知识卡片。仅当用户明确要求删除某张卡片时使用；本工具属于高风险写操作，执行前必须经过 harness 权限确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_id": {
                        "type": "string",
                        "description": "要删除的卡片 ID。",
                    }
                },
                "required": ["card_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_cards",
            "description": "列出当前用户最近保存的 Q&A 知识卡片。用于查看最近卡片、浏览知识库或选择要读取、更新、删除的卡片；返回摘要，不是完整回答依据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量，工具会限制到允许范围。",
                    },
                    "category": {
                        "type": "string",
                        "description": "可选硬过滤分类。只有用户明确限定分类时才传入；指定分类无结果时不要跨分类兜底。",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_duplicate_cards",
            "description": "检测当前用户疑似重复的 Q&A 知识卡片，只返回 duplicate 或 possible_duplicate 候选。用户主动查重、整理或合并时使用 mode=manual；保存或更新后的低打扰检测使用 mode=auto，且不得自动合并。",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["target", "all"],
                        "description": "target 检测指定卡片或文本；all 检测当前用户个人知识库全部 Q&A 卡片。",
                    },
                    "card_id": {
                        "type": "string",
                        "description": "以某张已有卡片为目标进行查重。",
                    },
                    "query": {
                        "type": "string",
                        "description": "未指定 card_id 时使用的查重查询文本。",
                    },
                    "category": {
                        "type": "string",
                        "description": "可选硬过滤分类。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回数量，工具会限制到允许范围。",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["manual", "auto"],
                        "description": "manual 表示用户主动查重；auto 表示保存或更新后的低打扰检测。",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge_qa_cards",
            "description": "合并当前用户的多张 Q&A 知识卡片：创建一张新卡片，并物理删除原卡片。仅当用户明确要求合并且已确认合并草案时使用；本工具属于高风险写操作，执行前必须经过 harness 权限确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要合并并删除的原卡片 ID，至少两张。",
                    },
                    "question": {
                        "type": "string",
                        "description": "合并后新卡片的问题，应综合原卡片且不要引入无来源内容。",
                    },
                    "answer": {
                        "type": "string",
                        "description": "合并后新卡片的答案，应综合原卡片且不要引入无来源内容。",
                    },
                    "summary": {
                        "type": "string",
                        "description": "合并后新卡片的摘要。",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "合并后新卡片的检索关键词，包括主题词、技术名词、项目名、工具名、API 名、模型名、数据库名、函数名或关键概念。",
                    },
                    "category": {
                        "type": "string",
                        "description": "合并后新卡片的唯一语义主分类。必须是具体稳定的短名词短语，不超过 24 个字符；不得使用兜底分类；不得使用函数名、字段名、模型名、数据库名、工具名或 API 名。",
                    },
                },
                "required": ["card_ids", "question", "answer", "summary", "keywords", "category"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rebuild_qa_semantic_index",
            "description": "为尚未向量化的历史 Q&A 卡片重建语义向量索引。用于维护或修复语义索引，不改变 Q&A 事实内容；不是普通问答检索工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "本次最多处理的未向量化卡片数量。",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
]
