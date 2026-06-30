from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .constants import QADataAccessConstants as qa_data_constants
from .qa_card_models import QACard


@dataclass(frozen=True)
class DuplicatePair:
    """A scored duplicate relation between two cards.

    Attributes:
        left_id: The first card id in the pair.
        right_id: The second card id in the pair.
        duplicate_score: Weighted similarity score for this pair.
        duplicate_level: Duplicate severity returned to the tool layer.
        reason: Human-readable explanation for why the pair was retained.
    """

    left_id: str
    right_id: str
    duplicate_score: float
    duplicate_level: str
    reason: str


@dataclass(frozen=True)
class DuplicateGroup:
    """A connected group of cards that share retained duplicate pairs.

    Attributes:
        card_ids: Stable card ids included in the group.
        duplicate_score: Highest pair score in the group.
        duplicate_level: Highest duplicate severity in the group.
        reason: Explanation copied from the strongest pair.
        cards: Full card objects for display payload construction.
    """

    card_ids: list[str]
    duplicate_score: float
    duplicate_level: str
    reason: str
    cards: list[QACard]


@dataclass(frozen=True)
class DuplicateDetectionResult:
    """The result of a full-library duplicate detection run.

    Attributes:
        checked_count: Number of cards inspected by the run.
        duplicate_groups: Groups that passed duplicate thresholds.
    """

    checked_count: int
    duplicate_groups: list[DuplicateGroup]


class DuplicateDetectionService:
    """Detects duplicate Q&A cards without calling the LLM."""

    def detect_all(
        self,
        cards: list[QACard],
        *,
        mode: str,
        limit: int,
    ) -> DuplicateDetectionResult:
        """Run full-library duplicate detection.

        Inputs:
            cards: Cards to inspect.
            mode: Detection strictness.
            limit: Maximum number of groups to return.
        Outputs:
            A DuplicateDetectionResult with checked count and duplicate groups.
        Side Effects:
            None.
        """
        pairs = self._score_pairs(cards, self._candidate_pairs(cards))
        if mode == qa_data_constants.DETECTION_MODE_AUTO:
            pairs = [
                pair
                for pair in pairs
                if pair.duplicate_level == qa_data_constants.DUPLICATE_LEVEL_DUPLICATE
            ]
        groups = self._build_groups(cards, pairs)
        return DuplicateDetectionResult(
            checked_count=len(cards),
            duplicate_groups=groups[:limit],
        )

    def _candidate_pairs(self, cards: list[QACard]) -> set[tuple[str, str]]:
        """Return card pairs that share enough indexed tokens to score."""
        card_tokens = {card.id: self._weighted_tokens(card) for card in cards}
        inverted: dict[str, list[str]] = {}
        for card_id, tokens in card_tokens.items():
            for token in tokens:
                inverted.setdefault(token, []).append(card_id)

        pair_weights: dict[tuple[str, str], float] = {}
        for token, card_ids in inverted.items():
            weight = (
                qa_data_constants.LONG_TOKEN_WEIGHT
                if len(token) >= qa_data_constants.LONG_TOKEN_MIN_LENGTH
                else qa_data_constants.SHORT_TOKEN_WEIGHT
            )
            for index, left_id in enumerate(card_ids):
                for right_id in card_ids[index + qa_data_constants.NEXT_INDEX_OFFSET :]:
                    pair = tuple(sorted((left_id, right_id)))
                    pair_weights[pair] = pair_weights.get(pair, qa_data_constants.NO_SCORE) + weight

        return {
            pair
            for pair, weight in pair_weights.items()
            if weight >= qa_data_constants.MIN_SHARED_TOKEN_WEIGHT
        }

    def _score_pairs(
        self,
        cards: list[QACard],
        pairs: set[tuple[str, str]],
    ) -> list[DuplicatePair]:
        """Score candidate pairs and keep pairs above duplicate thresholds."""
        cards_by_id = {card.id: card for card in cards}
        scored_pairs: list[DuplicatePair] = []
        for left_id, right_id in pairs:
            left = cards_by_id[left_id]
            right = cards_by_id[right_id]
            keyword_overlap = self._keyword_overlap(left, right)
            question_score = self._similarity(left.question, right.question)
            summary_score = self._similarity(left.summary, right.summary)
            answer_score = self._similarity(left.answer, right.answer)
            same_category = left.category == right.category
            duplicate_score = round(
                qa_data_constants.QUESTION_SCORE_WEIGHT * question_score
                + qa_data_constants.SUMMARY_SCORE_WEIGHT * summary_score
                + qa_data_constants.KEYWORD_SCORE_WEIGHT * keyword_overlap
                + qa_data_constants.ANSWER_SCORE_WEIGHT * answer_score
                + qa_data_constants.CATEGORY_SCORE_WEIGHT * (
                    qa_data_constants.CATEGORY_MATCH_BONUS
                    if same_category
                    else qa_data_constants.CATEGORY_MISMATCH_BONUS
                ),
                qa_data_constants.ROUND_DIGITS,
            )
            duplicate_level = self._duplicate_level(
                duplicate_score=duplicate_score,
                question_score=question_score,
                keyword_overlap=keyword_overlap,
                same_category=same_category,
            )
            if duplicate_level:
                scored_pairs.append(
                    DuplicatePair(
                        left_id=left_id,
                        right_id=right_id,
                        duplicate_score=duplicate_score,
                        duplicate_level=duplicate_level,
                        reason=self._reason(
                            same_category=same_category,
                            question_score=question_score,
                            summary_score=summary_score,
                            keyword_overlap=keyword_overlap,
                        ),
                    )
                )
        return sorted(scored_pairs, key=lambda pair: pair.duplicate_score, reverse=True)

    @staticmethod
    def _duplicate_level(
        *,
        duplicate_score: float,
        question_score: float,
        keyword_overlap: float,
        same_category: bool,
    ) -> str:
        """Classify a scored pair into a duplicate level or discard it."""
        if same_category and (
            duplicate_score >= qa_data_constants.DUPLICATE_GROUP_SCORE_THRESHOLD
            or question_score >= qa_data_constants.QUESTION_DUPLICATE_THRESHOLD
        ):
            return qa_data_constants.DUPLICATE_LEVEL_DUPLICATE
        if same_category and duplicate_score >= qa_data_constants.POSSIBLE_GROUP_SCORE_THRESHOLD:
            return qa_data_constants.DUPLICATE_LEVEL_POSSIBLE_DUPLICATE
        if same_category and keyword_overlap >= qa_data_constants.KEYWORD_POSSIBLE_THRESHOLD:
            return qa_data_constants.DUPLICATE_LEVEL_POSSIBLE_DUPLICATE
        if not same_category and duplicate_score >= qa_data_constants.CROSS_CATEGORY_GROUP_SCORE_THRESHOLD:
            return qa_data_constants.DUPLICATE_LEVEL_POSSIBLE_DUPLICATE
        return qa_data_constants.DUPLICATE_LEVEL_NONE

    def _build_groups(
        self,
        cards: list[QACard],
        pairs: list[DuplicatePair],
    ) -> list[DuplicateGroup]:
        """Merge duplicate pairs into connected duplicate groups."""
        cards_by_id = {card.id: card for card in cards}
        card_order = {card.id: index for index, card in enumerate(cards)}
        adjacency: dict[str, set[str]] = {}
        pair_by_ids: dict[tuple[str, str], DuplicatePair] = {}
        for pair in pairs:
            adjacency.setdefault(pair.left_id, set()).add(pair.right_id)
            adjacency.setdefault(pair.right_id, set()).add(pair.left_id)
            pair_by_ids[tuple(sorted((pair.left_id, pair.right_id)))] = pair

        visited: set[str] = set()
        groups: list[DuplicateGroup] = []
        for card_id in sorted(adjacency):
            if card_id in visited:
                continue
            component = self._component(card_id, adjacency, visited)
            component.sort(key=lambda item: card_order[item])
            component_pairs = [
                pair_by_ids[tuple(sorted((left_id, right_id)))]
                for index, left_id in enumerate(component)
                for right_id in component[index + qa_data_constants.NEXT_INDEX_OFFSET :]
                if tuple(sorted((left_id, right_id))) in pair_by_ids
            ]
            if not component_pairs:
                continue
            best_pair = max(component_pairs, key=lambda pair: pair.duplicate_score)
            level = (
                qa_data_constants.DUPLICATE_LEVEL_DUPLICATE
                if any(
                    pair.duplicate_level == qa_data_constants.DUPLICATE_LEVEL_DUPLICATE
                    for pair in component_pairs
                )
                else qa_data_constants.DUPLICATE_LEVEL_POSSIBLE_DUPLICATE
            )
            groups.append(
                DuplicateGroup(
                    card_ids=component,
                    duplicate_score=best_pair.duplicate_score,
                    duplicate_level=level,
                    reason=best_pair.reason,
                    cards=[cards_by_id[item] for item in component],
                )
            )
        return sorted(groups, key=lambda group: group.duplicate_score, reverse=True)

    @staticmethod
    def _component(
        start_id: str,
        adjacency: dict[str, set[str]],
        visited: set[str],
    ) -> list[str]:
        """Collect one connected component from the pair adjacency map."""
        stack = [start_id]
        component: list[str] = []
        while stack:
            card_id = stack.pop()
            if card_id in visited:
                continue
            visited.add(card_id)
            component.append(card_id)
            stack.extend(sorted(adjacency.get(card_id, set()) - visited))
        return sorted(component)

    @classmethod
    def _weighted_tokens(cls, card: QACard) -> set[str]:
        """Build recall tokens from comparable card fields."""
        tokens = set()
        for keyword in card.keywords:
            tokens.update(cls._text_terms(keyword))
            if keyword.strip():
                tokens.add(keyword.strip().lower())
        tokens.update(cls._text_terms(card.question))
        tokens.update(cls._text_terms(card.summary))
        return tokens

    @staticmethod
    def _keyword_overlap(left: QACard, right: QACard) -> float:
        """Return keyword overlap normalized by the larger keyword set."""
        left_keywords = {keyword.lower() for keyword in left.keywords}
        right_keywords = {keyword.lower() for keyword in right.keywords}
        if not left_keywords or not right_keywords:
            return qa_data_constants.NO_SCORE
        return len(left_keywords & right_keywords) / max(len(left_keywords), len(right_keywords))

    @classmethod
    def _text_terms(cls, text: str) -> set[str]:
        """Extract deterministic alphanumeric and Chinese recall terms."""
        clean = text.lower().strip()
        words = set(re.findall(r"[a-z0-9_]+", clean))
        chinese_chars = [
            character
            for character in clean
            if "\u4e00" <= character <= "\u9fff" and character not in qa_data_constants.COMMON_CHINESE_CHARS
        ]
        words.update(chinese_chars)
        words.update(
            "".join(chinese_chars[index : index + qa_data_constants.CHINESE_BIGRAM_WIDTH])
            for index in range(len(chinese_chars) - qa_data_constants.NEXT_INDEX_OFFSET)
        )
        return {word for word in words if word}

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        """Return deterministic string similarity for two text fields."""
        if not left.strip() or not right.strip():
            return qa_data_constants.NO_SCORE
        return SequenceMatcher(None, left.lower().strip(), right.lower().strip()).ratio()

    @staticmethod
    def _reason(
        *,
        same_category: bool,
        question_score: float,
        summary_score: float,
        keyword_overlap: float,
    ) -> str:
        """Build a concise display reason for a retained pair."""
        parts = []
        if same_category:
            parts.append("同分类")
        if question_score >= qa_data_constants.REASON_SIGNAL_THRESHOLD:
            parts.append("问题文本相似")
        if summary_score >= qa_data_constants.REASON_SIGNAL_THRESHOLD:
            parts.append("摘要相似")
        if keyword_overlap >= qa_data_constants.KEYWORD_REASON_THRESHOLD:
            parts.append("关键词重合")
        return "，".join(parts) if parts else "相似度达到查重阈值"
