class ToolRuntimeConstants:
    PERMISSION_BEHAVIOR_ALLOW = "allow"
    PERMISSION_BEHAVIOR_DENY = "deny"
    PERMISSION_BEHAVIOR_ASK = "ask"
    TOOL_SAVE_QA_CARD = "save_qa_card"
    TOOL_SEARCH_QA_CARDS = "search_qa_cards"
    TOOL_HYBRID_SEARCH_QA_CARDS = "hybrid_search_qa_cards"
    TOOL_READ_QA_CARD = "read_qa_card"
    TOOL_UPDATE_QA_CARD = "update_qa_card"
    TOOL_DELETE_QA_CARD = "delete_qa_card"
    TOOL_LIST_RECENT_CARDS = "list_recent_cards"
    TOOL_DETECT_DUPLICATE_CARDS = "detect_duplicate_cards"
    TOOL_MERGE_QA_CARDS = "merge_qa_cards"
    TOOL_REBUILD_QA_SEMANTIC_INDEX = "rebuild_qa_semantic_index"
    TOOL_CREATE_TODO = "create_todo"
    TOOL_LIST_TODOS = "list_todos"
    TOOL_UPDATE_TODO = "update_todo"
    TOOL_LIST_MEMORY_INDEX = "list_memory_index"
    TOOL_READ_MEMORY = "read_memory"
    RESULT_OK_FIELD = "ok"
    RESULT_ERROR_CODE_FIELD = "error_code"
    RESULT_MESSAGE_FIELD = "message"
    ERROR_CODE_UNKNOWN_TOOL = "unknown_tool"
    ERROR_CODE_TOOL_ERROR = "tool_error"
    ERROR_CODE_PERMISSION_DENIED = "permission_denied"
    TOOLS_REQUIRING_APPROVAL = {
        TOOL_UPDATE_QA_CARD: "This operation changes Q&A knowledge.",
        TOOL_DELETE_QA_CARD: "This operation deletes Q&A knowledge.",
        TOOL_MERGE_QA_CARDS: "This operation merges Q&A knowledge.",
        TOOL_UPDATE_TODO: "This operation changes a todo item.",
    }
    ERROR_OUTPUT_FIELDS = (RESULT_OK_FIELD, RESULT_ERROR_CODE_FIELD, RESULT_MESSAGE_FIELD)
    DISPLAY_INPUT_FIELDS: dict[str, tuple[str, ...]] = {
        "save_qa_card": ("question", "answer", "summary", "keywords", "category"),
        "search_qa_cards": ("query", "limit", "category"),
        "hybrid_search_qa_cards": ("query", "limit", "category"),
        "read_qa_card": ("card_id",),
        "update_qa_card": ("card_id", "question", "answer", "summary", "keywords", "category"),
        "delete_qa_card": ("card_id",),
        "list_recent_cards": ("limit", "category"),
        "detect_duplicate_cards": ("scope", "card_id", "query", "category", "limit", "mode"),
        "merge_qa_cards": ("card_ids", "question", "answer", "summary", "keywords", "category"),
        "rebuild_qa_semantic_index": ("limit",),
        "create_todo": ("title", "notes", "due_at"),
        "list_todos": ("query", "status", "limit"),
        "update_todo": ("todo_id", "title", "notes", "status", "due_at"),
        "list_memory_index": ("limit",),
        "read_memory": ("name",),
    }

    DISPLAY_OUTPUT_FIELDS: dict[str, tuple[str, ...]] = {
        "save_qa_card": ("ok", "card_id", "source_type", "created_at", "category", "error_code", "message"),
        "search_qa_cards": (
            "ok",
            "cards.card_id",
            "cards.question",
            "cards.summary",
            "cards.answer_snippet",
            "cards.score",
            "cards.source_type",
            "cards.created_at",
            "cards.category",
            "error_code",
            "message",
        ),
        "hybrid_search_qa_cards": (
            "ok",
            "cards.rank",
            "cards.card_id",
            "cards.question",
            "cards.summary",
            "cards.answer_snippet",
            "cards.score",
            "cards.final_score",
            "cards.match_level",
            "cards.matched_by",
            "cards.keyword_score",
            "cards.keyword_score_norm",
            "cards.semantic_score",
            "cards.source_type",
            "cards.created_at",
            "cards.category",
            "warning",
            "message",
            "error_code",
        ),
        "read_qa_card": (
            "ok",
            "card.card_id",
            "card.question",
            "card.answer",
            "card.summary",
            "card.keywords",
            "card.category",
            "card.source_type",
            "card.created_at",
            "card.updated_at",
            "error_code",
            "message",
        ),
        "update_qa_card": (
            "ok",
            "card.card_id",
            "card.question",
            "card.answer",
            "card.summary",
            "card.keywords",
            "card.category",
            "card.source_type",
            "card.created_at",
            "card.updated_at",
            "error_code",
            "message",
        ),
        "delete_qa_card": (
            "ok",
            "deleted_card_id",
            "error_code",
            "message",
        ),
        "list_recent_cards": (
            "ok",
            "cards.card_id",
            "cards.question",
            "cards.summary",
            "cards.keywords",
            "cards.category",
            "cards.source_type",
            "cards.created_at",
            "error_code",
            "message",
        ),
        "detect_duplicate_cards": (
            "ok",
            "scope",
            "checked_card_id",
            "checked_count",
            "candidates.card_id",
            "candidates.question",
            "candidates.summary",
            "candidates.category",
            "candidates.duplicate_score",
            "candidates.duplicate_level",
            "candidates.reason",
            "duplicate_groups.card_ids",
            "duplicate_groups.duplicate_score",
            "duplicate_groups.duplicate_level",
            "duplicate_groups.reason",
            "duplicate_groups.cards.card_id",
            "duplicate_groups.cards.question",
            "duplicate_groups.cards.summary",
            "duplicate_groups.cards.category",
            "warning",
            "error_code",
            "message",
        ),
        "merge_qa_cards": (
            "ok",
            "new_card_id",
            "deleted_card_ids",
            "source_type",
            "created_at",
            "category",
            "warning",
            "error_code",
            "message",
        ),
        "rebuild_qa_semantic_index": (
            "ok",
            "status",
            "message",
            "total",
            "indexed",
            "failed",
            "failed_card_ids",
            "error_code",
            "message",
        ),
        "create_todo": (
            "ok",
            "todo.todo_id",
            "todo.title",
            "todo.notes",
            "todo.status",
            "todo.due_at",
            "todo.created_at",
            "todo.updated_at",
            "error_code",
            "message",
        ),
        "list_todos": (
            "ok",
            "todos.todo_id",
            "todos.title",
            "todos.notes",
            "todos.status",
            "todos.due_at",
            "todos.created_at",
            "todos.updated_at",
            "error_code",
            "message",
        ),
        "update_todo": (
            "ok",
            "todo.todo_id",
            "todo.title",
            "todo.notes",
            "todo.status",
            "todo.due_at",
            "todo.created_at",
            "todo.updated_at",
            "error_code",
            "message",
        ),
        "list_memory_index": (
            "ok",
            "entries.name",
            "entries.type",
            "entries.description",
            "entries.path",
            "error_code",
            "message",
        ),
        "read_memory": (
            "ok",
            "memory.name",
            "memory.type",
            "memory.description",
            "memory.path",
            "memory.updated_at",
            "memory.source_type",
            "memory.content",
            "error_code",
            "message",
        ),
    }
