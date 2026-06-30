class PostgresConstants:
    FORBIDDEN_CATEGORIES = {"其他", "未分类", "杂项", "默认分类", "未知", "待分类"}
    DEFAULT_QA_SOURCE_TYPE = "manual_qa"
    QA_CARD_ID_PREFIX = "qa"
    DEFAULT_QA_LIMIT = 10
    DEFAULT_QA_SEARCH_LIMIT = 5
    MAX_QA_LIMIT = 50
    MAX_CATEGORY_LENGTH = 24
    SEARCH_RESULT_SCORE = 1
    SEARCH_SNIPPET_LENGTH = 160
    SEARCH_SNIPPET_ELLIPSIS = "..."
    TODO_STATUS_OPEN = "open"
    TODO_STATUS_DONE = "done"
    TODO_STATUS_CANCELED = "canceled"
    TODO_QUERY_STATUS_ALL = "all"
    TODO_STATUSES = {TODO_STATUS_OPEN, TODO_STATUS_DONE, TODO_STATUS_CANCELED}
    TODO_QUERY_STATUSES = {*TODO_STATUSES, TODO_QUERY_STATUS_ALL}
    DEFAULT_TODO_LIMIT = 20
    MAX_TODO_LIMIT = 50
    DEFAULT_SESSION_LIMIT = 20
    MAX_SESSION_LIMIT = 100
    DEFAULT_POOL_MIN_SIZE = 1
    DEFAULT_POOL_MAX_SIZE = 5
    SESSION_STATUS_IDLE = "idle"
    SESSION_STATUS_RUNNING = "running"
    DEFAULT_TOOL_RESULT_THRESHOLD_CHARS = 8000
    DEFAULT_RECENT_MESSAGES_COUNT = 12
    SESSION_TITLE_PREVIEW_CHARS = 30
    SESSION_MESSAGE_FIELD_ROLE = "role"
    SESSION_MESSAGE_ROLE_PATH = "message.role"
    SESSION_MESSAGE_ROW_FIELD_MESSAGE = "message"
    DEFAULT_MEMORY_TYPE = "user"
    MEMORY_FIELD_MEMORY_ID = "memory_id"
    MEMORY_FIELD_TITLE = "title"
    MEMORY_FIELD_SUMMARY = "summary"
    MEMORY_FIELD_CONTENT = "content"
    MEMORY_FIELD_UPDATED_AT = "updated_at"
    MEMORY_PATH_PREFIX = "postgres:agent_user_memories"
    MEMORY_SOURCE_TYPE_USER_PREFERENCE = "user_preference"
    EMBEDDING_STATUS_READY = "ready"
    EMBEDDING_STATUS_PENDING = "pending"
    EMBEDDING_STATUS_FAILED = "failed"
    EMBEDDING_STATUSES = {
        EMBEDDING_STATUS_PENDING,
        EMBEDDING_STATUS_READY,
        EMBEDDING_STATUS_FAILED,
    }
    POSTGRES_SCHEMA_STATEMENTS: tuple[str, ...] = (
        "CREATE EXTENSION IF NOT EXISTS vector",
        """
        CREATE TABLE IF NOT EXISTS users (
          user_id TEXT PRIMARY KEY,
          email TEXT NOT NULL UNIQUE,
          llm_provider_user_id TEXT NOT NULL UNIQUE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_login_codes (
          login_code_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          email TEXT NOT NULL,
          code_hash TEXT NOT NULL,
          expires_at TIMESTAMPTZ NOT NULL,
          purpose TEXT NOT NULL,
          consumed BOOLEAN NOT NULL DEFAULT false,
          consumed_at TIMESTAMPTZ,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
          session_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          token_hash TEXT NOT NULL UNIQUE,
          expires_at TIMESTAMPTZ NOT NULL,
          revoked_at TIMESTAMPTZ,
          last_seen_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS qa_cards (
          card_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          question TEXT NOT NULL,
          answer TEXT NOT NULL,
          summary TEXT NOT NULL,
          keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
          category TEXT NOT NULL,
          source_type TEXT NOT NULL,
          embedding vector,
          embedding_status TEXT NOT NULL DEFAULT 'pending',
          embedding_model TEXT,
          legacy_source TEXT,
          legacy_card_id TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (user_id, legacy_source, legacy_card_id),
          CHECK (embedding_status IN ('pending', 'ready', 'failed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS todo_items (
          todo_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          title TEXT NOT NULL,
          notes TEXT,
          status TEXT NOT NULL DEFAULT 'open',
          due_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (status IN ('open', 'done', 'canceled'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS conversation_sessions (
          session_id TEXT NOT NULL,
          user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          title TEXT,
          summary TEXT,
          status TEXT NOT NULL DEFAULT 'idle',
          current_run_id TEXT,
          last_prompt_usage_ratio DOUBLE PRECISION,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (user_id, session_id),
          CHECK (status IN ('idle', 'running'))
        )
        """,
        "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS last_prompt_usage_ratio DOUBLE PRECISION",
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
          message_id BIGSERIAL PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          session_id TEXT NOT NULL,
          sequence_no INTEGER NOT NULL,
          role TEXT NOT NULL,
          message JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          FOREIGN KEY (user_id, session_id)
            REFERENCES conversation_sessions(user_id, session_id)
            ON DELETE CASCADE,
          UNIQUE (user_id, session_id, sequence_no)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_user_memories (
          user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          memory_id TEXT NOT NULL,
          title TEXT NOT NULL,
          summary TEXT NOT NULL,
          content TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (user_id, memory_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_email_login_codes_user_id ON email_login_codes(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_email_login_codes_email_purpose_created_at ON email_login_codes(email, purpose, created_at DESC, login_code_id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_email_login_codes_expires_at ON email_login_codes(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_qa_cards_user_id_created_at ON qa_cards(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_todo_items_user_id_updated_at ON todo_items(user_id, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_user_id_updated_at ON conversation_sessions(user_id, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_user_session ON conversation_messages(user_id, session_id, sequence_no)",
        "CREATE INDEX IF NOT EXISTS idx_agent_user_memories_user_id_updated_at ON agent_user_memories(user_id, updated_at DESC)",
    )
