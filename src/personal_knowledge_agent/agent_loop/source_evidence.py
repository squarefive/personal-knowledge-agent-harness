from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


MAX_RENDERED_SOURCES = 5
SOURCE_HEADING_RE = re.compile(r"(?m)^来源[:：]\s*$")
UNSUPPORTED_CLAIMS = (
    "根据本地知识库",
    "根据知识卡片",
    "根据检索结果",
)


@dataclass(frozen=True)
class SourceEvidence:
    card_id: str
    question: str
    source_type: str
    created_at: str
    evidence_kind: str


@dataclass(frozen=True)
class TrustedAnswer:
    answer: str
    source_count: int
    removed_model_sources: bool = False
    removed_unsupported_claim: bool = False


def finalize_answer(answer: str, turn_messages: list[dict[str, Any]]) -> TrustedAnswer:
    sources = extract_sources(turn_messages)
    cleaned, removed_model_sources = remove_model_source_section(answer)
    removed_unsupported_claim = False

    if not sources:
        cleaned, removed_unsupported_claim = remove_unsupported_claims(cleaned)
        return TrustedAnswer(
            answer=cleaned,
            source_count=0,
            removed_model_sources=removed_model_sources,
            removed_unsupported_claim=removed_unsupported_claim,
        )

    rendered = f"{cleaned.rstrip()}\n\n{render_sources(sources)}"
    return TrustedAnswer(
        answer=rendered,
        source_count=len(sources),
        removed_model_sources=removed_model_sources,
    )


def extract_sources(turn_messages: list[dict[str, Any]]) -> list[SourceEvidence]:
    tool_arguments = _tool_arguments_by_id(turn_messages)
    sources: list[SourceEvidence] = []
    seen: set[str] = set()

    for message in turn_messages:
        if message.get("role") != "tool":
            continue
        tool_call_id = message.get("tool_call_id")
        if not isinstance(tool_call_id, str):
            continue
        tool_name, arguments = tool_arguments.get(tool_call_id, ("", {}))
        result = _parse_json_object(message.get("content"))
        if result.get("ok") is not True:
            continue
        for source in _sources_from_result(tool_name, arguments, result):
            if not source.card_id:
                continue
            if source.card_id in seen:
                continue
            seen.add(source.card_id)
            sources.append(source)
            if len(sources) >= MAX_RENDERED_SOURCES:
                return sources
    return sources


def render_sources(sources: list[SourceEvidence]) -> str:
    lines = ["来源："]
    for source in sources[:MAX_RENDERED_SOURCES]:
        lines.extend(
            [
                f"- card_id: {source.card_id}",
                f"  原始问题: {source.question}",
                f"  source_type: {source.source_type}",
                f"  created_at: {source.created_at}",
            ]
        )
    return "\n".join(lines)


def remove_model_source_section(answer: str) -> tuple[str, bool]:
    match = SOURCE_HEADING_RE.search(answer)
    if match is None:
        return answer.strip(), False
    return answer[: match.start()].rstrip(), True


def remove_unsupported_claims(answer: str) -> tuple[str, bool]:
    cleaned = answer
    removed = False
    for claim in UNSUPPORTED_CLAIMS:
        if claim in cleaned:
            cleaned = cleaned.replace(claim, "")
            removed = True
    lines = []
    for line in cleaned.splitlines():
        if re.search(r"\bcard_id\s*[:：]", line):
            removed = True
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip(), removed


def _tool_arguments_by_id(turn_messages: list[dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    tool_arguments: dict[str, tuple[str, dict[str, Any]]] = {}
    for message in turn_messages:
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = tool_call.get("id")
            function = tool_call.get("function")
            if not isinstance(tool_call_id, str) or not isinstance(function, dict):
                continue
            name = function.get("name")
            arguments = _parse_json_object(function.get("arguments"))
            if isinstance(name, str):
                tool_arguments[tool_call_id] = (name, arguments)
    return tool_arguments


def _sources_from_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> list[SourceEvidence]:
    if tool_name == "save_qa_card":
        question = arguments.get("question")
        return [_source_from_mapping(result, question=question, evidence_kind="saved")]
    if tool_name == "search_qa_cards":
        cards = result.get("cards")
        if not isinstance(cards, list):
            return []
        return [_source_from_mapping(card, evidence_kind="searched") for card in cards]
    if tool_name == "read_qa_card":
        card = result.get("card")
        if not isinstance(card, dict):
            return []
        return [_source_from_mapping(card, evidence_kind="read")]
    return []


def _source_from_mapping(
    payload: dict[str, Any],
    *,
    evidence_kind: str,
    question: Any | None = None,
) -> SourceEvidence:
    card_id = payload.get("card_id")
    source_question = question if question is not None else payload.get("question")
    source_type = payload.get("source_type")
    created_at = payload.get("created_at")
    if not all(isinstance(value, str) and value.strip() for value in (card_id, source_question, source_type, created_at)):
        return SourceEvidence("", "", "", "", "")
    return SourceEvidence(
        card_id=card_id.strip(),
        question=source_question.strip(),
        source_type=source_type.strip(),
        created_at=created_at.strip(),
        evidence_kind=evidence_kind,
    )


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
