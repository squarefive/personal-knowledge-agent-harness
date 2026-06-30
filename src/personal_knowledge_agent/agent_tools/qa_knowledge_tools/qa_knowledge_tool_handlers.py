from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from ...llm_clients.constants import LLMClientConstants as llm_constants
from ...qa_data_access import QACard, SearchResult, SemanticSearchHit
from ...qa_data_access.duplicate_detection import DuplicateDetectionService, DuplicateGroup
from .constants import QAKnowledgeToolConstants as qa_constants


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
        limit: int = qa_constants.DEFAULT_SEARCH_LIMIT,
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

    def list_recent_cards(
        self,
        limit: int = qa_constants.DEFAULT_RECENT_LIMIT,
        category: str | None = None,
    ) -> list[QACard]: ...

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
    match_level: str = qa_constants.MATCH_LEVEL_DISCARD
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
            question = self._required_text(arguments, qa_constants.ARG_QUESTION)
            answer = self._required_text(arguments, qa_constants.ARG_ANSWER)
            summary = self._required_text(arguments, qa_constants.ARG_SUMMARY)
            keywords = self._required_keywords(arguments)
            category = self._required_text(arguments, qa_constants.ARG_CATEGORY)
            card = self.store.save_card(
                question=question,
                answer=answer,
                summary=summary,
                keywords=keywords,
                category=category,
            )
            result = {
                qa_constants.OUTPUT_OK: True,
                qa_constants.OUTPUT_CARD_ID: card.id,
                qa_constants.OUTPUT_SOURCE_TYPE: card.source_type,
                qa_constants.OUTPUT_CREATED_AT: card.created_at,
                qa_constants.OUTPUT_CATEGORY: card.category,
            }
            warning = self._try_upsert_semantic_index(card)
            if warning:
                result[qa_constants.OUTPUT_WARNING] = warning
            return result
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._required_text(arguments, qa_constants.ARG_QUERY)
            limit = self._optional_limit(arguments, default=qa_constants.DEFAULT_SEARCH_LIMIT)
            category = self._optional_category(arguments)
            cards = self.store.search_cards(query, limit=limit, category=category)
            return {qa_constants.OUTPUT_OK: True, qa_constants.OUTPUT_CARDS: [asdict(card) for card in cards]}
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def hybrid_search_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query = self._required_text(arguments, qa_constants.ARG_QUERY)
            limit = self._optional_limit(arguments, default=qa_constants.DEFAULT_SEARCH_LIMIT)
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
                    semantic_limit = (
                        max(limit * qa_constants.OVER_FETCH_MULTIPLIER, qa_constants.MIN_OVER_FETCH_LIMIT)
                        if category is not None
                        else limit
                    )
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
            elif not semantic_degraded and returned_candidates[0].match_level == qa_constants.MATCH_LEVEL_WEAK:
                warning = "只找到弱相关候选，回答前应读取完整卡片并谨慎判断。"

            cards = self.store.read_cards_by_ids([candidate.card_id for candidate in returned_candidates])
            candidate_by_card_id = {candidate.card_id: candidate for candidate in returned_candidates}
            payload = {
                qa_constants.OUTPUT_OK: True,
                qa_constants.OUTPUT_CARDS: [
                    self._search_payload(card, candidate_by_card_id[card.id], rank=index + 1)
                    for index, card in enumerate(cards[:limit])
                ],
            }
            if warning:
                payload[qa_constants.OUTPUT_WARNING] = warning
            if message:
                payload[qa_constants.OUTPUT_MESSAGE] = message
            return payload
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def read_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_id = self._required_text(arguments, qa_constants.ARG_CARD_ID)
            card = self.store.read_card(card_id)
            if card is None:
                return self._error(qa_constants.ERROR_CODE_NOT_FOUND, f"card not found: {card_id}")
            return {qa_constants.OUTPUT_OK: True, qa_constants.OUTPUT_CARD: self._card_payload(card)}
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def update_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_id = self._required_text(arguments, qa_constants.ARG_CARD_ID)
            patch = self._update_patch(arguments)
            card = self.store.update_card(card_id, **patch)
            if card is None:
                return self._error(qa_constants.ERROR_CODE_NOT_FOUND, f"card not found: {card_id}")
            result = {qa_constants.OUTPUT_OK: True, qa_constants.OUTPUT_CARD: self._card_payload(card)}
            warning = self._try_upsert_semantic_index(card)
            if warning:
                result[qa_constants.OUTPUT_WARNING] = warning
            return result
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def delete_qa_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_id = self._required_text(arguments, qa_constants.ARG_CARD_ID)
            deleted = self.store.delete_card(card_id)
            if not deleted:
                return self._error(qa_constants.ERROR_CODE_NOT_FOUND, f"card not found: {card_id}")
            result = {qa_constants.OUTPUT_OK: True, qa_constants.OUTPUT_DELETED_CARD_ID: card_id}
            warning = self._try_delete_semantic_index(card_id)
            if warning:
                result[qa_constants.OUTPUT_WARNING] = warning
            return result
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def rebuild_qa_semantic_index(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = (
                self._optional_limit(arguments, default=qa_constants.DEFAULT_REBUILD_LIMIT)
                if qa_constants.ARG_LIMIT in arguments
                else None
            )
            if self.semantic_index is None or not self.semantic_index.is_enabled():
                return {
                    qa_constants.OUTPUT_OK: True,
                    qa_constants.OUTPUT_STATUS: qa_constants.REBUILD_STATUS_DISABLED,
                    qa_constants.OUTPUT_MESSAGE: f"缺少 {llm_constants.DASHSCOPE_API_KEY_ENV}，无法向量化历史卡片。",
                    qa_constants.OUTPUT_TOTAL: 0,
                    qa_constants.OUTPUT_INDEXED: 0,
                    qa_constants.OUTPUT_FAILED: 0,
                    qa_constants.OUTPUT_FAILED_CARD_IDS: [],
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
                qa_constants.OUTPUT_OK: True,
                qa_constants.OUTPUT_STATUS: (
                    qa_constants.REBUILD_STATUS_OK
                    if not failed_card_ids
                    else qa_constants.REBUILD_STATUS_PARTIAL_FAILED
                ),
                qa_constants.OUTPUT_TOTAL: len(cards),
                qa_constants.OUTPUT_INDEXED: indexed,
                qa_constants.OUTPUT_FAILED: len(failed_card_ids),
                qa_constants.OUTPUT_FAILED_CARD_IDS: failed_card_ids,
            }
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def list_recent_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = self._optional_limit(arguments, default=qa_constants.DEFAULT_RECENT_LIMIT)
            category = self._optional_category(arguments)
            cards = self.store.list_recent_cards(limit=limit, category=category)
            return {
                qa_constants.OUTPUT_OK: True,
                qa_constants.OUTPUT_CARDS: [self._recent_payload(card) for card in cards],
            }
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_STORE_ERROR, str(exc))

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
            limit = self._optional_limit(arguments, default=qa_constants.DEFAULT_SEARCH_LIMIT)
            scope = self._duplicate_scope(arguments)
            mode = self._duplicate_mode(arguments)
            category = self._optional_category(arguments)
            if scope == qa_constants.DUPLICATE_SCOPE_ALL:
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
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

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
            qa_constants.OUTPUT_OK: True,
            qa_constants.OUTPUT_SCOPE: qa_constants.DUPLICATE_SCOPE_ALL,
            qa_constants.OUTPUT_CHECKED_COUNT: result.checked_count,
            qa_constants.OUTPUT_DUPLICATE_GROUPS: [
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
            over_fetch_limit = max(limit * qa_constants.OVER_FETCH_MULTIPLIER, qa_constants.MIN_OVER_FETCH_LIMIT)
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
            if mode == qa_constants.DUPLICATE_MODE_AUTO:
                candidates = [
                    item
                    for item in candidates
                    if item[1].duplicate_level == qa_constants.DUPLICATE_LEVEL_DUPLICATE
                ]
            payload = {
                qa_constants.OUTPUT_OK: True,
                qa_constants.OUTPUT_SCOPE: qa_constants.DUPLICATE_SCOPE_TARGET,
                qa_constants.OUTPUT_CHECKED_CARD_ID: checked_card_id,
                qa_constants.OUTPUT_CANDIDATES: [
                    self._duplicate_payload(card, candidate)
                    for card, candidate in candidates[:limit]
                ],
            }
            if warning:
                payload[qa_constants.OUTPUT_WARNING] = warning
            return payload
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def merge_qa_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            card_ids = self._required_card_ids(arguments)
            original_cards = self.store.read_cards_by_ids(card_ids)
            found_card_ids = {card.id for card in original_cards}
            missing_card_ids = [card_id for card_id in card_ids if card_id not in found_card_ids]
            if missing_card_ids:
                return self._error(qa_constants.ERROR_CODE_NOT_FOUND, f"cards not found: {', '.join(missing_card_ids)}")

            question = self._required_text(arguments, qa_constants.ARG_QUESTION)
            answer = self._required_text(arguments, qa_constants.ARG_ANSWER)
            summary = self._required_text(arguments, qa_constants.ARG_SUMMARY)
            keywords = self._required_keywords(arguments)
            category = self._required_text(arguments, qa_constants.ARG_CATEGORY)
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
                qa_constants.OUTPUT_OK: True,
                qa_constants.OUTPUT_NEW_CARD_ID: new_card.id,
                qa_constants.OUTPUT_DELETED_CARD_IDS: card_ids,
                qa_constants.OUTPUT_SOURCE_TYPE: new_card.source_type,
                qa_constants.OUTPUT_CREATED_AT: new_card.created_at,
                qa_constants.OUTPUT_CATEGORY: new_card.category,
            }
            if warnings:
                result[qa_constants.OUTPUT_WARNING] = "；".join(warnings)
            return result
        except Exception as exc:
            return self._error(qa_constants.ERROR_CODE_INVALID_INPUT, str(exc))

    def definitions(self) -> list[dict[str, Any]]:
        return qa_constants.QA_KNOWLEDGE_TOOL_DEFINITIONS

    @staticmethod
    def _required_text(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _required_keywords(arguments: dict[str, Any]) -> list[str]:
        value = arguments.get(qa_constants.ARG_KEYWORDS)
        if not isinstance(value, list):
            raise ValueError("keywords must be a list of strings")
        keywords = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not keywords:
            raise ValueError("keywords must contain at least one non-empty string")
        return keywords

    @staticmethod
    def _optional_limit(arguments: dict[str, Any], default: int) -> int:
        value = arguments.get(qa_constants.ARG_LIMIT, default)
        if not isinstance(value, int) or value < 1:
            return default
        return min(value, qa_constants.MAX_LIMIT)

    def _optional_category(self, arguments: dict[str, Any]) -> str | None:
        if qa_constants.ARG_CATEGORY not in arguments or arguments.get(qa_constants.ARG_CATEGORY) is None:
            return None
        return self.store.validate_category(self._required_text(arguments, qa_constants.ARG_CATEGORY))

    def _optional_target_card(self, arguments: dict[str, Any]) -> QACard | None:
        if qa_constants.ARG_CARD_ID not in arguments or arguments.get(qa_constants.ARG_CARD_ID) is None:
            return None
        card_id = self._required_text(arguments, qa_constants.ARG_CARD_ID)
        card = self.store.read_card(card_id)
        if card is None:
            raise ValueError(f"card not found: {card_id}")
        return card

    @staticmethod
    def _duplicate_scope(arguments: dict[str, Any]) -> str:
        """Return the validated duplicate detection scope."""
        scope = arguments.get(qa_constants.ARG_SCOPE, qa_constants.DUPLICATE_SCOPE_TARGET)
        if scope not in (qa_constants.DUPLICATE_SCOPE_TARGET, qa_constants.DUPLICATE_SCOPE_ALL):
            raise ValueError("scope must be target or all")
        return scope

    @staticmethod
    def _duplicate_mode(arguments: dict[str, Any]) -> str:
        mode = arguments.get(qa_constants.ARG_MODE, qa_constants.DUPLICATE_MODE_MANUAL)
        if mode not in (qa_constants.DUPLICATE_MODE_MANUAL, qa_constants.DUPLICATE_MODE_AUTO):
            raise ValueError("mode must be manual or auto")
        return mode

    def _duplicate_query(self, arguments: dict[str, Any], target_card: QACard | None) -> str:
        query = arguments.get(qa_constants.ARG_QUERY)
        if isinstance(query, str) and query.strip():
            return query.strip()
        if target_card is not None:
            return " ".join([target_card.question, target_card.summary, *target_card.keywords, target_card.category])
        raise ValueError("card_id or query must be provided")

    @staticmethod
    def _required_card_ids(arguments: dict[str, Any]) -> list[str]:
        value = arguments.get(qa_constants.ARG_CARD_IDS)
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
        for name in (qa_constants.ARG_QUESTION, qa_constants.ARG_ANSWER, qa_constants.ARG_SUMMARY):
            value = arguments.get(name)
            if value is not None:
                patch[name] = self._required_text(arguments, name)
        if qa_constants.ARG_KEYWORDS in arguments:
            patch[qa_constants.ARG_KEYWORDS] = self._required_keywords(arguments)
        if qa_constants.ARG_CATEGORY in arguments:
            patch[qa_constants.ARG_CATEGORY] = self._required_text(arguments, qa_constants.ARG_CATEGORY)
        if not patch:
            raise ValueError("at least one field must be provided")
        return patch

    @staticmethod
    def _card_payload(card: QACard) -> dict[str, Any]:
        return {
            qa_constants.OUTPUT_CARD_ID: card.id,
            qa_constants.OUTPUT_QUESTION: card.question,
            qa_constants.OUTPUT_ANSWER: card.answer,
            qa_constants.OUTPUT_SUMMARY: card.summary,
            qa_constants.OUTPUT_KEYWORDS: card.keywords,
            qa_constants.OUTPUT_CATEGORY: card.category,
            qa_constants.OUTPUT_SOURCE_TYPE: card.source_type,
            qa_constants.OUTPUT_CREATED_AT: card.created_at,
            qa_constants.OUTPUT_UPDATED_AT: card.updated_at,
        }

    @staticmethod
    def _recent_payload(card: QACard) -> dict[str, Any]:
        return {
            qa_constants.OUTPUT_CARD_ID: card.id,
            qa_constants.OUTPUT_QUESTION: card.question,
            qa_constants.OUTPUT_SUMMARY: card.summary,
            qa_constants.OUTPUT_KEYWORDS: card.keywords,
            qa_constants.OUTPUT_CATEGORY: card.category,
            qa_constants.OUTPUT_SOURCE_TYPE: card.source_type,
            qa_constants.OUTPUT_CREATED_AT: card.created_at,
        }

    @staticmethod
    def _search_payload(
        card: QACard,
        candidate: QAKnowledgeSearchCandidate,
        *,
        rank: int,
    ) -> dict[str, Any]:
        return {
            qa_constants.OUTPUT_RANK: rank,
            qa_constants.OUTPUT_CARD_ID: card.id,
            qa_constants.OUTPUT_QUESTION: card.question,
            qa_constants.OUTPUT_SUMMARY: card.summary,
            qa_constants.OUTPUT_ANSWER_SNIPPET: QAKnowledgeToolHandlers._snippet(card.answer),
            qa_constants.OUTPUT_SCORE: candidate.final_score,
            qa_constants.OUTPUT_FINAL_SCORE: candidate.final_score,
            qa_constants.OUTPUT_MATCH_LEVEL: candidate.match_level,
            qa_constants.OUTPUT_MATCHED_BY: candidate.matched_by or [],
            qa_constants.OUTPUT_KEYWORD_SCORE: candidate.keyword_score,
            qa_constants.OUTPUT_KEYWORD_SCORE_NORM: candidate.keyword_score_norm,
            qa_constants.OUTPUT_SEMANTIC_SCORE: candidate.semantic_score,
            qa_constants.OUTPUT_SOURCE_TYPE: card.source_type,
            qa_constants.OUTPUT_CREATED_AT: card.created_at,
            qa_constants.OUTPUT_CATEGORY: card.category,
        }

    @staticmethod
    def _duplicate_payload(card: QACard, candidate: DuplicateCandidate) -> dict[str, Any]:
        return {
            qa_constants.OUTPUT_CARD_ID: card.id,
            qa_constants.OUTPUT_QUESTION: card.question,
            qa_constants.OUTPUT_SUMMARY: card.summary,
            qa_constants.OUTPUT_CATEGORY: card.category,
            qa_constants.OUTPUT_DUPLICATE_SCORE: candidate.duplicate_score,
            qa_constants.OUTPUT_DUPLICATE_LEVEL: candidate.duplicate_level,
            qa_constants.OUTPUT_SEMANTIC_SCORE: candidate.semantic_score,
            qa_constants.OUTPUT_KEYWORD_SCORE_NORM: candidate.keyword_score_norm,
            qa_constants.OUTPUT_KEYWORD_OVERLAP: candidate.keyword_overlap,
            qa_constants.OUTPUT_QUESTION_OVERLAP: candidate.question_overlap,
            qa_constants.OUTPUT_SAME_CATEGORY: candidate.same_category,
            qa_constants.OUTPUT_REASON: candidate.reason,
        }

    @staticmethod
    def _duplicate_group_payload(group: DuplicateGroup) -> dict[str, Any]:
        """Return the tool payload for one duplicate group."""
        return {
            qa_constants.OUTPUT_CARD_IDS: group.card_ids,
            qa_constants.OUTPUT_DUPLICATE_SCORE: group.duplicate_score,
            qa_constants.OUTPUT_DUPLICATE_LEVEL: group.duplicate_level,
            qa_constants.OUTPUT_REASON: group.reason,
            qa_constants.OUTPUT_CARDS: [
                {
                    qa_constants.OUTPUT_CARD_ID: card.id,
                    qa_constants.OUTPUT_QUESTION: card.question,
                    qa_constants.OUTPUT_SUMMARY: card.summary,
                    qa_constants.OUTPUT_CATEGORY: card.category,
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
            candidate.add_match(qa_constants.MATCH_SOURCE_KEYWORD)
        for card_id, score in semantic_scores.items():
            candidate = candidates.setdefault(card_id, QAKnowledgeSearchCandidate(card_id=card_id))
            candidate.semantic_score = score
            candidate.add_match(qa_constants.MATCH_SOURCE_SEMANTIC)

        max_keyword_score = max((candidate.keyword_score for candidate in candidates.values()), default=0.0)
        for candidate in candidates.values():
            candidate.keyword_score_norm = (
                candidate.keyword_score / max_keyword_score if max_keyword_score > 0 else 0.0
            )
            if use_keyword_only_score:
                candidate.final_score = candidate.keyword_score_norm
            else:
                candidate.final_score = (
                    qa_constants.KEYWORD_SCORE_WEIGHT * candidate.keyword_score_norm
                    + qa_constants.SEMANTIC_SCORE_WEIGHT * candidate.semantic_score
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
        category_bonus = (
            qa_constants.CATEGORY_MATCH_BONUS if candidate.same_category else qa_constants.CATEGORY_MISMATCH_BONUS
        )
        score = (
            qa_constants.DUPLICATE_SEMANTIC_WEIGHT * candidate.semantic_score
            + qa_constants.DUPLICATE_KEYWORD_OVERLAP_WEIGHT * candidate.keyword_overlap
            + qa_constants.DUPLICATE_QUESTION_OVERLAP_WEIGHT * candidate.question_overlap
            + qa_constants.DUPLICATE_CATEGORY_WEIGHT * category_bonus
        )
        return round(score, qa_constants.SCORE_ROUND_DIGITS)

    @staticmethod
    def _duplicate_level(candidate: DuplicateCandidate) -> str:
        if candidate.same_category and (
            candidate.semantic_score >= qa_constants.DUPLICATE_SEMANTIC_THRESHOLD
            or candidate.duplicate_score >= qa_constants.DUPLICATE_SCORE_THRESHOLD
        ):
            return qa_constants.DUPLICATE_LEVEL_DUPLICATE
        if candidate.same_category and candidate.duplicate_score >= qa_constants.POSSIBLE_DUPLICATE_SCORE_THRESHOLD:
            return qa_constants.DUPLICATE_LEVEL_POSSIBLE
        if (
            candidate.same_category
            and candidate.keyword_score_norm >= qa_constants.POSSIBLE_DUPLICATE_KEYWORD_SCORE_THRESHOLD
            and candidate.keyword_overlap >= qa_constants.POSSIBLE_DUPLICATE_KEYWORD_OVERLAP_THRESHOLD
        ):
            return qa_constants.DUPLICATE_LEVEL_POSSIBLE
        if (
            not candidate.same_category
            and candidate.semantic_score >= qa_constants.POSSIBLE_CROSS_CATEGORY_SEMANTIC_THRESHOLD
        ):
            return qa_constants.DUPLICATE_LEVEL_POSSIBLE
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
        return round(
            len(target_keywords & candidate_keywords) / max(len(target_keywords), len(candidate_keywords)),
            qa_constants.SCORE_ROUND_DIGITS,
        )

    @classmethod
    def _text_overlap(cls, left: str, right: str) -> float:
        left_terms = cls._text_terms(left)
        right_terms = cls._text_terms(right)
        if not left_terms or not right_terms:
            return 0.0
        return round(
            len(left_terms & right_terms) / max(len(left_terms), len(right_terms)),
            qa_constants.SCORE_ROUND_DIGITS,
        )

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
        normal = [
            candidate
            for candidate in candidates
            if candidate.match_level in (qa_constants.MATCH_LEVEL_STRONG, qa_constants.MATCH_LEVEL_MEDIUM)
        ]
        if normal:
            return normal[:limit]
        weak = [candidate for candidate in candidates if candidate.match_level == qa_constants.MATCH_LEVEL_WEAK]
        return weak[:qa_constants.WEAK_CANDIDATE_LIMIT]

    @staticmethod
    def _match_level(final_score: float) -> str:
        if final_score >= qa_constants.STRONG_MATCH_THRESHOLD:
            return qa_constants.MATCH_LEVEL_STRONG
        if final_score >= qa_constants.MEDIUM_MATCH_THRESHOLD:
            return qa_constants.MATCH_LEVEL_MEDIUM
        if final_score >= qa_constants.WEAK_MATCH_THRESHOLD:
            return qa_constants.MATCH_LEVEL_WEAK
        return qa_constants.MATCH_LEVEL_DISCARD

    @staticmethod
    def _snippet(answer: str, length: int = qa_constants.SNIPPET_LENGTH) -> str:
        clean = " ".join(answer.split())
        if len(clean) <= length:
            return clean
        return f"{clean[: length - len(qa_constants.SNIPPET_ELLIPSIS)]}{qa_constants.SNIPPET_ELLIPSIS}"

    @staticmethod
    def _error(error_code: str, message: str) -> dict[str, Any]:
        return {
            qa_constants.OUTPUT_OK: False,
            qa_constants.OUTPUT_ERROR_CODE: error_code,
            qa_constants.OUTPUT_MESSAGE: message,
        }
