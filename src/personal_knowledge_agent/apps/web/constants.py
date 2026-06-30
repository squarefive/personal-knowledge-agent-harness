class WebConstants:
    DATABASE_URL_ENV = "DATABASE_URL"
    SMTP_HOST_ENV = "SMTP_HOST"
    SMTP_USER_ENV = "SMTP_USER"
    SMTP_PASSWORD_ENV = "SMTP_PASSWORD"
    MAIL_FROM_ENV = "MAIL_FROM"
    RESULT_OK_FIELD = "ok"
    RESULT_ERROR_CODE_FIELD = "error_code"
    RESULT_MESSAGE_FIELD = "message"
    RESULT_EMAIL_FIELD = "email"
    RESULT_USER_FIELD = "user"
    RESULT_SESSION_FIELD = "session"
    RESULT_SESSIONS_FIELD = "sessions"
    RESULT_MESSAGES_FIELD = "messages"
    RUN_ID_FIELD = "run_id"
    EVENT_TYPE_FIELD = "event_type"
    TIMESTAMP_FIELD = "timestamp"
    APPROVAL_ID_FIELD = "approval_id"
    APPROVAL_STATUS_FIELD = "status"
    ANSWER_FIELD = "answer"
    SUMMARY_FIELD = "summary"
    EXPIRES_AT_FIELD = "expires_at"
    TIMEOUT_SECONDS_FIELD = "timeout_seconds"
    MESSAGE_ROLE_FIELD = "role"
    MESSAGE_CONTENT_FIELD = "content"
    MESSAGE_CREATED_AT_FIELD = "created_at"
    MESSAGE_TOOL_CALLS_FIELD = "tool_calls"
    MESSAGE_TOOL_CALL_ID_FIELD = "tool_call_id"
    MESSAGE_ROLE_USER = "user"
    MESSAGE_ROLE_ASSISTANT = "assistant"
    MESSAGE_ROLE_TOOL = "tool"
    DISPLAY_MESSAGE_ROLE_ASSISTANT_RUN = "assistant_run"
    DISPLAY_EVENT_ID_FIELD = "event_id"
    DISPLAY_STEPS_FIELD = "steps"
    APPROVAL_SUMMARY_TITLE_FIELD = "title"
    APPROVAL_SUMMARY_TOOL_NAME_FIELD = "tool_name"
    APPROVAL_SUMMARY_TOOL_LABEL_FIELD = "tool_label"
    APPROVAL_SUMMARY_TARGET_LABEL_FIELD = "target_label"
    APPROVAL_SUMMARY_TARGET_FIELD = "target"
    APPROVAL_SUMMARY_CHANGES_FIELD = "changes"
    APPROVAL_SUMMARY_PREVIEW_FIELD = "preview"
    APPROVAL_SUMMARY_RISK_FIELD = "risk"
    APPROVAL_SUMMARY_REASON_FIELD = "reason"
    EVENT_ERROR = "error"
    EVENT_ANSWER_DELTA = "answer_delta"
    EVENT_PROMPT_USAGE_UPDATED = "prompt_usage_updated"
    EVENT_PERMISSION_REQUESTED = "permission_requested"
    EVENT_PERMISSION_RESOLVED = "permission_resolved"
    EVENT_FINAL_ANSWER_GENERATED = "final_answer_generated"
    UNKNOWN_EVENT_TYPE = "unknown"
    APPROVAL_DECISION_APPROVE = "approve"
    APPROVAL_DECISION_DENY = "deny"
    APPROVAL_STATUS_PENDING = "pending"
    APPROVAL_STATUS_APPROVED = "approved"
    APPROVAL_STATUS_DENIED = "denied"
    APPROVAL_STATUS_EXPIRED = "expired"
    APPROVAL_STATUS_CANCELLED = "cancelled"
    APPROVAL_ID_PREFIX = "approval"
    MEDIA_TYPE_EVENT_STREAM = "text/event-stream"
    ERROR_INVALID_INPUT = "invalid_input"
    ERROR_APPROVAL_NOT_FOUND = "approval_not_found"
    ERROR_AUTH_NOT_CONFIGURED = "auth_not_configured"
    ERROR_AUTH_REQUEST = "auth_request_error"
    ERROR_AUTH_VERIFY = "auth_verify_error"
    ERROR_AUTH_ME = "auth_me_error"
    ERROR_AUTH_LOGOUT = "auth_logout_error"
    ERROR_NOT_AUTHENTICATED = "not_authenticated"
    ERROR_SESSION_STORE_NOT_CONFIGURED = "session_store_not_configured"
    ERROR_SESSION_NOT_FOUND = "session_not_found"
    ERROR_SESSION_RENAME = "session_rename_error"
    ERROR_SESSION_READ = "session_read_error"
    ERROR_SESSION_BUSY = "session_busy"
    ERROR_AGENT = "agent_error"
    ERROR_CARD_READ = "card_read_error"
    ERROR_CARD_SEARCH = "card_search_error"
    ERROR_PERMISSION_DENIED = "permission_denied"
    MESSAGE_AUTH_NOT_CONFIGURED = "authentication is not configured"
    MESSAGE_AUTHENTICATION_REQUIRED = "authentication is required"
    MESSAGE_AUTHENTICATION_SESSION_MISSING = "authentication session is missing"
    MESSAGE_AUTH_REQUEST_FAILED = "login code request failed"
    MESSAGE_AUTH_VERIFY_FAILED = "login code verification failed"
    MESSAGE_AUTH_LOOKUP_FAILED = "authentication lookup failed"
    MESSAGE_AUTH_LOGOUT_FAILED = "logout failed"
    MESSAGE_APPROVAL_DECISION_INVALID = "decision must be approve or deny"
    MESSAGE_APPROVAL_NOT_PENDING = "approval request is not pending"
    MESSAGE_SESSION_STORE_NOT_CONFIGURED = "cloud session repository is not configured"
    MESSAGE_SESSION_NOT_FOUND = "session not found"
    MESSAGE_CHAT_MESSAGE_REQUIRED = "message must be a non-empty string"
    MESSAGE_SESSION_BUSY = "current session is already running"
    MESSAGE_CARD_QUERY_REQUIRED = "q must be a non-empty string"
    SESSION_ID_SUFFIX_CHARS = 12
    THREAD_JOIN_TIMEOUT_SECONDS = 1
    APPROVAL_TIMEOUT_SECONDS = 300
    APPROVAL_SUMMARY_TEXT_LIMIT = 180
    APPROVAL_SUMMARY_ELLIPSIS = "..."
    DEFAULT_CARD_LIMIT = 10
    MIN_CARD_LIMIT = 1
    MAX_CARD_LIMIT = 50
    CARD_TOOL_QUERY_FIELD = "query"
    CARD_TOOL_LIMIT_FIELD = "limit"
    CARD_TOOL_CARD_ID_FIELD = "card_id"
    DELETE_TOOL_NAME = "delete_qa_card"
    UPDATE_TOOL_NAME = "update_qa_card"
    MERGE_TOOL_NAME = "merge_qa_cards"
    CARD_ID_FIELD = "card_id"
    CARD_IDS_FIELD = "card_ids"
    QUESTION_FIELD = "question"
    KEYWORDS_FIELD = "keywords"
    CATEGORY_FIELD = "category"
    UPDATE_PREVIEW_FIELDS = (
        QUESTION_FIELD,
        ANSWER_FIELD,
        SUMMARY_FIELD,
        CATEGORY_FIELD,
        KEYWORDS_FIELD,
    )
    UPDATE_CHANGE_FIELD_LABELS = (
        (QUESTION_FIELD, "原始问题"),
        (ANSWER_FIELD, "原始答案"),
        (SUMMARY_FIELD, "摘要"),
        (KEYWORDS_FIELD, "关键词"),
        (CATEGORY_FIELD, "分类"),
    )
    AUTH_COOKIE_NAME = "pka_session"
    DEFAULT_SESSION_ID = "default"
    SESSION_ID_PREFIX = "session"
    DEFAULT_SESSION_TITLE = "新会话"
    TITLE_SOURCE_AUTO = "auto"
    TITLE_SOURCE_USER = "user"
    DEFAULT_TOOL_DISPLAY_NAME = "调用工具"
    TODO_DISPLAY_STATUS_OPEN = "open"
    DEFAULT_WEB_HOST = "127.0.0.1"
    DEFAULT_WEB_PORT = 8787
    BROWSER_OPEN_DELAY_SECONDS = 0.8
    UVICORN_LOG_LEVEL = "info"
    MIN_COOKIE_MAX_AGE_SECONDS = 0
    MIN_EXPIRES_MINUTES = 1
    SECONDS_PER_MINUTE = 60
    MIN_PROMPT_USAGE_RATIO = 0.0
    MAX_PROMPT_USAGE_RATIO = 1.0
    TOOL_DISPLAY_NAMES = {
        "hybrid_search_qa_cards": "搜索知识库",
        "search_qa_cards": "搜索知识库",
        "save_qa_card": "保存知识卡片",
        "read_qa_card": "读取知识卡片",
        "list_recent_cards": "读取最近卡片",
        "update_qa_card": "更新知识卡片",
        "delete_qa_card": "删除知识卡片",
        "merge_qa_cards": "合并知识卡片",
        "create_todo": "保存待办",
        "list_todos": "查询待办",
        "update_todo": "更新待办",
    }
