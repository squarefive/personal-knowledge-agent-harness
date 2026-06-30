from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .constants import AgentRuntimeConstants as runtime_constants


@dataclass(frozen=True)
class SourceEvidence:
    card_id: str
    question: str
    source_type: str
    created_at: str
    created_at_display: str
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
        if message.get(runtime_constants.MESSAGE_ROLE_FIELD) != runtime_constants.MESSAGE_ROLE_TOOL:
            continue
        tool_call_id = message.get(runtime_constants.TOOL_CALL_ID_FIELD)
        if not isinstance(tool_call_id, str):
            continue
        tool_name, arguments = tool_arguments.get(tool_call_id, ("", {}))
        result = _parse_json_object(message.get(runtime_constants.MESSAGE_CONTENT_FIELD))
        if result.get(runtime_constants.RESULT_OK_FIELD) is not True:
            continue
        for source in _sources_from_result(tool_name, arguments, result):
            if not source.card_id:
                continue
            if source.card_id in seen:
                continue
            seen.add(source.card_id)
            sources.append(source)
            if len(sources) >= runtime_constants.MAX_RENDERED_SOURCES:
                return sources
    return sources


def render_sources(sources: list[SourceEvidence]) -> str:
    lines = ["来源："]
    for source in sources[:runtime_constants.MAX_RENDERED_SOURCES]:
        lines.extend(
            [
                f"- card_id: {source.card_id}",
                f"  原始问题: {source.question}",
                f"  source_type: {source.source_type}",
                f"  created_at: {source.created_at_display}",
            ]
        )
    return "\n".join(lines)


def remove_model_source_section(answer: str) -> tuple[str, bool]:
    match = runtime_constants.SOURCE_HEADING_RE.search(answer)
    if match is None:
        return answer.strip(), False
    return answer[: match.start()].rstrip(), True


def remove_unsupported_claims(answer: str) -> tuple[str, bool]:
    cleaned = answer
    removed = False
    for claim in runtime_constants.UNSUPPORTED_CLAIMS:
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
        if message.get(runtime_constants.MESSAGE_ROLE_FIELD) != runtime_constants.MESSAGE_ROLE_ASSISTANT:
            continue
        for tool_call in message.get(runtime_constants.MESSAGE_TOOL_CALLS_FIELD) or []:
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = tool_call.get(runtime_constants.TOOL_CALL_ID_PAYLOAD_FIELD)
            function = tool_call.get(runtime_constants.TOOL_CALL_FUNCTION_FIELD)
            if not isinstance(tool_call_id, str) or not isinstance(function, dict):
                continue
            name = function.get(runtime_constants.TOOL_CALL_NAME_FIELD)
            arguments = _parse_json_object(function.get(runtime_constants.TOOL_CALL_ARGUMENTS_FIELD))
            if isinstance(name, str):
                tool_arguments[tool_call_id] = (name, arguments)
    return tool_arguments


def _sources_from_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> list[SourceEvidence]:
    if tool_name == runtime_constants.TOOL_SAVE_QA_CARD:
        question = arguments.get(runtime_constants.RESULT_QUESTION_FIELD)
        return [_source_from_mapping(result, question=question, evidence_kind=runtime_constants.EVIDENCE_KIND_SAVED)]
    if tool_name in runtime_constants.SEARCH_SOURCE_TOOL_NAMES:
        cards = result.get(runtime_constants.RESULT_CARDS_FIELD)
        if not isinstance(cards, list):
            return []
        return [_source_from_mapping(card, evidence_kind=runtime_constants.EVIDENCE_KIND_SEARCHED) for card in cards]
    if tool_name == runtime_constants.TOOL_READ_QA_CARD:
        card = result.get(runtime_constants.RESULT_CARD_FIELD)
        if not isinstance(card, dict):
            return []
        return [_source_from_mapping(card, evidence_kind=runtime_constants.EVIDENCE_KIND_READ)]
    return []


def _source_from_mapping(
    payload: dict[str, Any],
    *,
    evidence_kind: str,
    question: Any | None = None,
) -> SourceEvidence:
    card_id = payload.get(runtime_constants.RESULT_CARD_ID_FIELD)
    source_question = question if question is not None else payload.get(runtime_constants.RESULT_QUESTION_FIELD)
    source_type = payload.get(runtime_constants.RESULT_SOURCE_TYPE_FIELD)
    created_at = payload.get(runtime_constants.RESULT_CREATED_AT_FIELD)
    if not all(isinstance(value, str) and value.strip() for value in (card_id, source_question, source_type, created_at)):
        return SourceEvidence("", "", "", "", "", "")
    created_at_text = created_at.strip()
    return SourceEvidence(
        card_id=card_id.strip(),
        question=source_question.strip(),
        source_type=source_type.strip(),
        created_at=created_at_text,
        created_at_display=_format_source_timestamp(created_at_text),
        evidence_kind=evidence_kind,
    )


def _format_source_timestamp(value: str) -> str:
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(runtime_constants.SOURCE_TIMEZONE).strftime("%Y/%m/%d %H:%M:%S (UTC+8)")


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
