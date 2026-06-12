from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from personal_knowledge_agent.qa_store import SQLiteStore
from personal_knowledge_agent.schemas import LLMResponse


def load_backfill_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "backfill-qa-categories.py"
    spec = importlib.util.spec_from_file_location("backfill_qa_categories", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCategoryClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, *, messages, tools, system_prompt):
        self.calls.append({"messages": messages, "tools": tools, "system_prompt": system_prompt})
        return LLMResponse(text=self.responses.pop(0))


def create_legacy_store(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteStore(db_path)
    card = store.save_card(
        question="历史问题？",
        answer="历史答案。",
        summary="历史摘要。",
        keywords=["历史"],
        category="Agent 开发",
    )
    with store._connect() as conn:
        conn.execute("ALTER TABLE qa_cards RENAME TO qa_cards_old")
        conn.execute(
            """
            CREATE TABLE qa_cards (
              id TEXT PRIMARY KEY,
              question TEXT NOT NULL,
              answer TEXT NOT NULL,
              summary TEXT NOT NULL,
              keywords TEXT NOT NULL,
              source_type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              is_vectorized INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO qa_cards (
              id, question, answer, summary, keywords, source_type, created_at, updated_at, is_vectorized
            )
            SELECT id, question, answer, summary, keywords, source_type, created_at, updated_at, is_vectorized
            FROM qa_cards_old
            """
        )
        conn.execute("DROP TABLE qa_cards_old")
    return SQLiteStore(db_path), card.id


def test_parse_category_strips_prefix_and_rejects_fallback():
    module = load_backfill_module()

    assert module.parse_category("分类：检索与知识库\n说明：ignored") == "检索与知识库"

    try:
        module.parse_category("其他")
    except ValueError:
        pass
    else:
        raise AssertionError("expected fallback category to be rejected")


def test_backfill_writes_categories_and_enforces_constraints(tmp_path, monkeypatch):
    module = load_backfill_module()
    store, card_id = create_legacy_store(tmp_path)
    enforced = []
    monkeypatch.setattr(store, "enforce_category_constraints", lambda: enforced.append(True))

    result = module.backfill_categories(
        store=store,
        client=FakeCategoryClient(["检索与知识库"]),
        enforce_constraints=True,
    )

    assert result.total == 1
    assert result.updated == 1
    assert result.failed == 0
    assert store.read_card(card_id).category == "检索与知识库"
    assert enforced == [True]


def test_backfill_failure_does_not_enforce_constraints(tmp_path, monkeypatch):
    module = load_backfill_module()
    store, card_id = create_legacy_store(tmp_path)
    enforced = []
    monkeypatch.setattr(store, "enforce_category_constraints", lambda: enforced.append(True))

    result = module.backfill_categories(
        store=store,
        client=FakeCategoryClient(["其他"]),
        enforce_constraints=True,
    )

    assert result.total == 1
    assert result.updated == 0
    assert result.failed == 1
    assert result.failed_card_ids == [card_id]
    assert store.read_card(card_id).category == ""
    assert enforced == []
