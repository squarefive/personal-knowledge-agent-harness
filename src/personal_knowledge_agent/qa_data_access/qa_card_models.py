from dataclasses import dataclass


@dataclass(frozen=True)
class QACard:
    id: str
    question: str
    answer: str
    summary: str
    keywords: list[str]
    category: str
    source_type: str
    created_at: str
    updated_at: str
    is_vectorized: int = 0


@dataclass(frozen=True)
class SearchResult:
    card_id: str
    question: str
    summary: str
    answer_snippet: str
    score: int
    source_type: str
    created_at: str
    category: str
