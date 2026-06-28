from __future__ import annotations

from dataclasses import replace
from typing import Any

from personal_knowledge_agent.agent_context.agent_profile_memory import MemoryDocument, MemoryIndex, MemoryIndexEntry
from personal_knowledge_agent.agent_context.conversation_sessions import CompactRecord, RuntimeCompactionResult, SessionMetadata
from personal_knowledge_agent.qa_data_access import QACard, SearchResult
from personal_knowledge_agent.todo_data_access import TodoItem


class InMemoryQACardStore:
    def __init__(self):
        self.cards: list[QACard] = []
        self.next_id = 1

    def save_card(
        self,
        *,
        question: str,
        answer: str,
        summary: str,
        keywords: list[str],
        category: str,
    ) -> QACard:
        now = f"2026-06-28T00:00:{self.next_id:02d}+00:00"
        card = QACard(
            id=f"qa_{self.next_id}",
            question=question,
            answer=answer,
            summary=summary,
            keywords=list(keywords),
            category=self.validate_category(category),
            source_type="manual_qa",
            created_at=now,
            updated_at=now,
        )
        self.next_id += 1
        self.cards.append(card)
        return card

    def search_cards(self, query: str, limit: int = 5, category: str | None = None) -> list[SearchResult]:
        results: list[SearchResult] = []
        for card in self._matching_cards(category=category):
            score = self._score(query, card)
            if score <= 0:
                continue
            results.append(
                SearchResult(
                    card_id=card.id,
                    question=card.question,
                    summary=card.summary,
                    answer_snippet=card.answer[:160],
                    score=score,
                    source_type=card.source_type,
                    created_at=card.created_at,
                    category=card.category,
                )
            )
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def read_card(self, card_id: str) -> QACard | None:
        return next((card for card in self.cards if card.id == card_id), None)

    def update_card(
        self,
        card_id: str,
        *,
        question: str | None = None,
        answer: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        category: str | None = None,
    ) -> QACard | None:
        for index, card in enumerate(self.cards):
            if card.id != card_id:
                continue
            updated = replace(
                card,
                question=question if question is not None else card.question,
                answer=answer if answer is not None else card.answer,
                summary=summary if summary is not None else card.summary,
                keywords=list(keywords) if keywords is not None else card.keywords,
                category=self.validate_category(category) if category is not None else card.category,
                updated_at="2026-06-28T00:10:00+00:00",
            )
            self.cards[index] = updated
            return updated
        return None

    def delete_card(self, card_id: str) -> bool:
        before = len(self.cards)
        self.cards = [card for card in self.cards if card.id != card_id]
        return len(self.cards) != before

    def list_recent_cards(self, limit: int = 10, category: str | None = None) -> list[QACard]:
        return list(reversed(self._matching_cards(category=category)))[:limit]

    def list_all_cards(self, category: str | None = None) -> list[QACard]:
        return self._matching_cards(category=category)

    def list_unvectorized_cards(self, limit: int | None = None) -> list[QACard]:
        cards = [card for card in self.cards if not card.is_vectorized]
        return cards[:limit] if limit is not None else cards

    def read_cards_by_ids(self, card_ids: list[str], category: str | None = None) -> list[QACard]:
        allowed = set(card_ids)
        return [card for card in self.cards if card.id in allowed and (category is None or card.category == category)]

    def mark_card_vectorized(self, card_id: str) -> bool:
        for index, card in enumerate(self.cards):
            if card.id == card_id:
                self.cards[index] = replace(card, is_vectorized=1)
                return True
        return False

    def validate_category(self, category: str) -> str:
        value = category.strip()
        if not value:
            raise ValueError("category must be a non-empty string")
        if value in {"其他", "未分类", "杂项", "默认分类", "未知", "待分类"}:
            raise ValueError("category must be specific")
        if len(value) > 24:
            raise ValueError("category must be 24 characters or fewer")
        return value

    def _matching_cards(self, *, category: str | None) -> list[QACard]:
        return [card for card in self.cards if category is None or card.category == category]

    @staticmethod
    def _score(query: str, card: QACard) -> int:
        query_lower = query.lower()
        haystack = " ".join([card.question, card.answer, card.summary, *card.keywords, card.category]).lower()
        score = 0
        for token in query_lower.split():
            if token and token in haystack:
                score += 1
        if query_lower and query_lower in haystack:
            score += 1
        for keyword in card.keywords:
            if keyword.lower() in query_lower:
                score += 2
        return score


class InMemoryTodoStore:
    def __init__(self):
        self.todos: list[TodoItem] = []
        self.next_id = 1

    def create_todo(self, *, title: str, notes: str | None = None, due_at: str | None = None) -> TodoItem:
        now = f"2026-06-28T01:00:{self.next_id:02d}+00:00"
        todo = TodoItem(
            id=f"todo_{self.next_id}",
            title=title,
            notes=notes or "",
            status="open",
            due_at=due_at,
            created_at=now,
            updated_at=now,
        )
        self.next_id += 1
        self.todos.append(todo)
        return todo

    def list_todos(self, *, query: str | None = None, status: str | None = "open", limit: int = 20) -> list[TodoItem]:
        todos = self.todos
        if status and status != "all":
            todos = [todo for todo in todos if todo.status == status]
        if query:
            query_lower = query.lower()
            todos = [todo for todo in todos if query_lower in todo.title.lower() or query_lower in todo.notes.lower()]
        return todos[:limit]

    def update_todo(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        notes: str | None = None,
        status: str | None = None,
        due_at: str | None = None,
        clear_due_at: bool = False,
    ) -> TodoItem | None:
        for index, todo in enumerate(self.todos):
            if todo.id != todo_id:
                continue
            updated = replace(
                todo,
                title=title if title is not None else todo.title,
                notes=notes if notes is not None else todo.notes,
                status=status if status is not None else todo.status,
                due_at=None if clear_due_at else (due_at if due_at is not None else todo.due_at),
                updated_at="2026-06-28T01:10:00+00:00",
            )
            self.todos[index] = updated
            return updated
        return None


class InMemoryMemoryStore:
    def __init__(self, documents: list[MemoryDocument] | None = None):
        self.documents = {document.name: document for document in documents or []}

    def load(self) -> MemoryIndex:
        return MemoryIndex(
            [
                MemoryIndexEntry(
                    name=document.name,
                    type=document.type,
                    description=document.description,
                    path=document.path,
                )
                for document in self.documents.values()
            ]
        )

    def read_by_entry(self, entry: MemoryIndexEntry) -> MemoryDocument:
        return self.documents[entry.name]


class InMemoryTranscript:
    def __init__(self):
        self.messages: list[dict[str, Any]] = []

    def append_message(self, message: dict[str, Any]) -> int:
        self.messages.append(dict(message))
        return len(self.messages)

    def load_messages(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def event_count(self) -> int:
        return len(self.messages)


class InMemoryMetadataStore:
    def __init__(self, *, model: str = "test-model", session_id: str = "default"):
        self.model = model
        self.session_id = session_id
        self.summary: str | None = None
        self.event_count = 0
        self.message_count = 0

    def load_or_create(self) -> SessionMetadata:
        return SessionMetadata(
            session_id=self.session_id,
            created_at="2026-06-28T02:00:00+00:00",
            updated_at="2026-06-28T02:00:00+00:00",
            cwd="memory",
            model=self.model,
            transcript_path="postgres://transcript",
            summary_path="postgres://summary",
            artifacts_dir="postgres://artifacts",
            event_count=self.event_count,
            message_count=self.message_count,
        )

    def update_counts(self, **kwargs: Any) -> SessionMetadata:
        self.event_count = kwargs.get("event_count", self.event_count)
        self.message_count = kwargs.get("message_count", self.message_count)
        return self.load_or_create()

    def update_after_user_message(self, message: str, *, event_count: int, message_count: int) -> SessionMetadata:
        self.event_count = event_count
        self.message_count = message_count
        return self.load_or_create()

    def update_summary(self, summary: str | None) -> bool:
        self.summary = summary
        return True


class InMemoryToolResultCompactor:
    def __init__(self, *, threshold_chars: int = 20):
        self.threshold_chars = threshold_chars
        self.records: list[CompactRecord] = []

    def compact_tool_result(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        result_text: str,
    ) -> CompactRecord | None:
        if len(result_text) <= self.threshold_chars:
            return None
        record = CompactRecord(
            artifact_path=f"postgres://artifacts/{tool_call_id}.json",
            summary=result_text[:80],
            relevance="tool result compacted for test",
        )
        self.records.append(record)
        return record


class InMemoryRuntimeContextCompactor:
    def __init__(self, *, summarizer: Any, recent_messages_count: int = 1):
        self.summarizer = summarizer
        self.recent_messages_count = recent_messages_count

    def compact(
        self,
        messages: list[dict[str, Any]],
        *,
        existing_summary: str | None = None,
    ) -> RuntimeCompactionResult:
        summary, _ = self.summarizer.summarize(messages)
        return RuntimeCompactionResult(
            messages=messages[-self.recent_messages_count :],
            session_summary=summary,
            mode="summary_plus_recent",
        )
