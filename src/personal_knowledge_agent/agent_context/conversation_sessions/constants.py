import re


class ConversationSessionConstants:
    DEFAULT_SESSION_TITLE = "新会话"
    TITLE_SOURCE_AUTO = "auto"
    TITLE_SOURCE_USER = "user"
    SUMMARY_STATUS_NONE = "none"
    SUMMARY_STATUS_VALID = "valid"
    SUMMARY_STATUS_FAILED = "failed"
    RESTORE_MODE_FULL = "full"
    RESTORE_MODE_SUMMARY_PLUS_RECENT = "summary_plus_recent"
    RESTORE_MODE_FIRST_AND_RECENT = "first_and_recent"
    RESTORE_MODE_RECENT_WITH_RECOVERY_NOTICE = "recent_with_recovery_notice"
    MESSAGE_ROLE_FIELD = "role"
    MESSAGE_ROLE_USER = "user"
    MESSAGE_CONTENT_FIELD = "content"
    SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    RESTORE_MESSAGE_BUDGET_CHARS = 120_000
    RESTORE_FIRST_MESSAGES_COUNT = 6
    RESTORE_RECENT_MESSAGES_COUNT = 12
    SUMMARY_MAX_RETRIES = 3
    SUMMARY_SYSTEM_PROMPT = "\n".join(
        [
            "你负责把过长的 Agent 会话 transcript 压缩为可恢复的 session summary。",
            "必须输出固定 Markdown 规格，包含 # Session Summary 以及所有要求的二级标题。",
            "保留当前目标、用户约束、重要上下文、已完成工作和下一步。",
            "不要编造 transcript 中不存在的信息。",
            "不要包含 API key、secret 或完整内部 payload。",
            "Boundaries 必须说明 summary 不是用户新请求、不是长期 memory、不是 Q&A 知识来源。",
        ]
    )
    REQUIRED_SUMMARY_HEADINGS = (
        "# Session Summary",
        "## Current Goal",
        "## User Constraints",
        "## Known Context",
        "## Completed Work",
        "## Next Step",
        "## Boundaries",
    )
    REQUIRED_BOUNDARY_STATEMENTS = (
        "不是用户新请求",
        "不是长期 memory",
        "不是 Q&A 知识来源",
    )
