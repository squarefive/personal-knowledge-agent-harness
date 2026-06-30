from datetime import timedelta, timezone
import re


class AgentRuntimeConstants:
    DEFAULT_CONTEXT_WINDOW_TOKENS = 1_000_000
    RUNTIME_COMPACT_USAGE_THRESHOLD = 0.75
    RECENT_MESSAGES_COUNT = 12
    DEFAULT_MAX_TURNS = 8
    MILLISECONDS_PER_SECOND = 1000
    MAX_RENDERED_SOURCES = 5
    MESSAGE_ROLE_FIELD = "role"
    MESSAGE_ROLE_USER = "user"
    MESSAGE_ROLE_ASSISTANT = "assistant"
    MESSAGE_ROLE_TOOL = "tool"
    MESSAGE_CONTENT_FIELD = "content"
    MESSAGE_TOOL_CALLS_FIELD = "tool_calls"
    TOOL_CALL_TYPE_FIELD = "type"
    TOOL_CALL_TYPE_FUNCTION = "function"
    TOOL_CALL_ID_FIELD = "tool_call_id"
    TOOL_CALL_ID_PAYLOAD_FIELD = "id"
    TOOL_CALL_FUNCTION_FIELD = "function"
    TOOL_CALL_NAME_FIELD = "name"
    TOOL_CALL_ARGUMENTS_FIELD = "arguments"
    RESULT_OK_FIELD = "ok"
    RESULT_COMPACT_RECORD_FIELD = "compact_record"
    RESULT_CARDS_FIELD = "cards"
    RESULT_CARD_FIELD = "card"
    RESULT_CARD_ID_FIELD = "card_id"
    RESULT_QUESTION_FIELD = "question"
    RESULT_SOURCE_TYPE_FIELD = "source_type"
    RESULT_CREATED_AT_FIELD = "created_at"
    TOOL_SAVE_QA_CARD = "save_qa_card"
    TOOL_SEARCH_QA_CARDS = "search_qa_cards"
    TOOL_LIST_RECENT_CARDS = "list_recent_cards"
    TOOL_HYBRID_SEARCH_QA_CARDS = "hybrid_search_qa_cards"
    TOOL_READ_QA_CARD = "read_qa_card"
    RUNTIME_COMPACTION_REASON_CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
    SEARCH_SOURCE_TOOL_NAMES = {
        TOOL_SEARCH_QA_CARDS,
        TOOL_LIST_RECENT_CARDS,
        TOOL_HYBRID_SEARCH_QA_CARDS,
    }
    EVIDENCE_KIND_SAVED = "saved"
    EVIDENCE_KIND_SEARCHED = "searched"
    EVIDENCE_KIND_READ = "read"
    SOURCE_HEADING_RE = re.compile(r"(?m)^来源[:：]\s*$")
    SOURCE_TIMEZONE = timezone(timedelta(hours=8))
    UNSUPPORTED_CLAIMS = (
        "根据本地知识库",
        "根据知识卡片",
        "根据检索结果",
    )
