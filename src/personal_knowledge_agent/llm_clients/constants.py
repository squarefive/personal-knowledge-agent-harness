from urllib import error
import ssl


class LLMClientConstants:
    DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
    DASHSCOPE_API_KEY_ENV = "DASHSCOPE_API_KEY"
    DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
    DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    DEFAULT_TIMEOUT_SECONDS = 60
    DEFAULT_MAX_RETRIES = 2
    DEFAULT_RETRY_BACKOFF_SECONDS = (0.5, 1.0)
    MESSAGE_ROLE_FIELD = "role"
    MESSAGE_ROLE_SYSTEM = "system"
    MESSAGE_CONTENT_FIELD = "content"
    PAYLOAD_MODEL_FIELD = "model"
    PAYLOAD_MESSAGES_FIELD = "messages"
    PAYLOAD_TOOLS_FIELD = "tools"
    PAYLOAD_TOOL_CHOICE_FIELD = "tool_choice"
    TOOL_CHOICE_AUTO = "auto"
    PAYLOAD_STREAM_FIELD = "stream"
    PAYLOAD_STREAM_OPTIONS_FIELD = "stream_options"
    PAYLOAD_INCLUDE_USAGE_FIELD = "include_usage"
    PAYLOAD_USER_ID_FIELD = "user_id"
    RESPONSE_USAGE_FIELD = "usage"
    RESPONSE_CHOICES_FIELD = "choices"
    RESPONSE_DELTA_FIELD = "delta"
    RESPONSE_TOOL_CALLS_FIELD = "tool_calls"
    RESPONSE_TOOL_CALL_INDEX_FIELD = "index"
    RESPONSE_TOOL_CALL_ID_FIELD = "id"
    RESPONSE_TOOL_CALL_FUNCTION_FIELD = "function"
    RESPONSE_TOOL_CALL_NAME_FIELD = "name"
    RESPONSE_TOOL_CALL_ARGUMENTS_FIELD = "arguments"
    RESPONSE_PROMPT_TOKENS_FIELD = "prompt_tokens"
    RESPONSE_COMPLETION_TOKENS_FIELD = "completion_tokens"
    RESPONSE_TOTAL_TOKENS_FIELD = "total_tokens"
    DEFAULT_QWEN_HTTP_TIMEOUT_SECONDS = 30.0
    RETRYABLE_HTTP_STATUSES = {429, 500, 503}
    RETRYABLE_NETWORK_ERRORS = (error.URLError, TimeoutError, ssl.SSLError, ConnectionError)
    CONTEXT_LIMIT_ERROR_MARKERS = (
        "context length exceeded",
        "context_length_exceeded",
        "token limit exceeded",
        "maximum context length",
    )
