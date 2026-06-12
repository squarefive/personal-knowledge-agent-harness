from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from personal_knowledge_agent.config import load_config
from personal_knowledge_agent.llm_client import DeepSeekClient
from personal_knowledge_agent.qa_store.sqlite_store import SQLiteStore
from personal_knowledge_agent.schemas import LLMResponse, QACard


CATEGORY_SYSTEM_PROMPT = "\n".join(
    [
        "你负责为本地 Q&A 知识卡片生成 category。",
        "category 是卡片唯一的语义主归属分类，不是关键词。",
        "只输出 category 本身，不要解释。",
        "category 必须是 1-24 个字符的短名词短语。",
        "不得输出：其他、未分类、杂项、默认分类、未知、待分类。",
        "不得输出函数名、字段名、模型名、数据库名、工具名或 API 名。",
        "推荐方向包括：Agent 开发、LLM 基础、工具调用、上下文管理、Prompt 工程、检索与知识库、向量检索、知识治理、数据存储、AI 编程经验、工程架构、调试排错、开发工具、框架选型、权限机制、项目使用说明。",
    ]
)


class CategoryLLM(Protocol):
    def chat(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str,
    ) -> LLMResponse:
        ...


@dataclass(frozen=True)
class BackfillResult:
    total: int
    updated: int
    failed: int
    failed_card_ids: list[str]


def parse_category(text: str | None) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty category response")
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`").strip()
    for prefix in ("category:", "Category:", "分类:", "分类：", "category："):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :].strip()
            break
    clean = clean.splitlines()[0].strip().strip('"').strip("'")
    return SQLiteStore.validate_category(clean)


def build_user_prompt(card: QACard) -> str:
    return "\n".join(
        [
            f"question: {card.question}",
            f"answer: {card.answer}",
            f"summary: {card.summary}",
            f"keywords: {', '.join(card.keywords)}",
        ]
    )


def generate_category(client: CategoryLLM, card: QACard) -> str:
    response = client.chat(
        messages=[{"role": "user", "content": build_user_prompt(card)}],
        tools=[],
        system_prompt=CATEGORY_SYSTEM_PROMPT,
    )
    return parse_category(response.text)


def backfill_categories(
    *,
    store: SQLiteStore,
    client: CategoryLLM,
    enforce_constraints: bool = True,
) -> BackfillResult:
    cards = store.list_cards_missing_category()
    failed_card_ids: list[str] = []
    updates: list[tuple[str, str]] = []
    for card in cards:
        try:
            updates.append((card.id, generate_category(client, card)))
        except Exception:
            failed_card_ids.append(card.id)

    if failed_card_ids:
        return BackfillResult(
            total=len(cards),
            updated=0,
            failed=len(failed_card_ids),
            failed_card_ids=failed_card_ids,
        )

    for card_id, category in updates:
        store.set_card_category(card_id, category)

    if enforce_constraints:
        store.enforce_category_constraints()

    return BackfillResult(total=len(cards), updated=len(updates), failed=0, failed_card_ids=[])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill qa_cards.category using DeepSeek.")
    parser.add_argument("--env", default=".env", help="Path to .env file.")
    parser.add_argument(
        "--skip-enforce",
        action="store_true",
        help="Only write missing categories; do not rebuild the table constraints.",
    )
    args = parser.parse_args(argv)

    config = load_config(Path(args.env))
    store = SQLiteStore(config.knowledge_db_path)
    client = DeepSeekClient(api_key=config.deepseek_api_key, model=config.deepseek_model)
    result = backfill_categories(
        store=store,
        client=client,
        enforce_constraints=not args.skip_enforce,
    )
    print(
        {
            "total": result.total,
            "updated": result.updated,
            "failed": result.failed,
            "failed_card_ids": result.failed_card_ids,
        }
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
