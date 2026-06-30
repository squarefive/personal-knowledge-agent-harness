from typing import Any


class QAKnowledgeToolConstants:
    ARG_ANSWER = "answer"
    ARG_CARD_ID = "card_id"
    ARG_CARD_IDS = "card_ids"
    ARG_CATEGORY = "category"
    ARG_KEYWORDS = "keywords"
    ARG_LIMIT = "limit"
    ARG_MODE = "mode"
    ARG_QUERY = "query"
    ARG_QUESTION = "question"
    ARG_SCOPE = "scope"
    ARG_SUMMARY = "summary"
    ERROR_CODE_INVALID_INPUT = "invalid_input"
    ERROR_CODE_NOT_FOUND = "not_found"
    ERROR_CODE_STORE_ERROR = "store_error"
    OUTPUT_ANSWER = "answer"
    OUTPUT_ANSWER_SNIPPET = "answer_snippet"
    OUTPUT_CARD = "card"
    OUTPUT_CARD_ID = "card_id"
    OUTPUT_CARD_IDS = "card_ids"
    OUTPUT_CARDS = "cards"
    OUTPUT_CANDIDATES = "candidates"
    OUTPUT_CATEGORY = "category"
    OUTPUT_CHECKED_CARD_ID = "checked_card_id"
    OUTPUT_CHECKED_COUNT = "checked_count"
    OUTPUT_CREATED_AT = "created_at"
    OUTPUT_DELETED_CARD_ID = "deleted_card_id"
    OUTPUT_DELETED_CARD_IDS = "deleted_card_ids"
    OUTPUT_DUPLICATE_GROUPS = "duplicate_groups"
    OUTPUT_DUPLICATE_LEVEL = "duplicate_level"
    OUTPUT_DUPLICATE_SCORE = "duplicate_score"
    OUTPUT_ERROR_CODE = "error_code"
    OUTPUT_FAILED = "failed"
    OUTPUT_FAILED_CARD_IDS = "failed_card_ids"
    OUTPUT_FINAL_SCORE = "final_score"
    OUTPUT_INDEXED = "indexed"
    OUTPUT_KEYWORD_OVERLAP = "keyword_overlap"
    OUTPUT_KEYWORD_SCORE = "keyword_score"
    OUTPUT_KEYWORD_SCORE_NORM = "keyword_score_norm"
    OUTPUT_KEYWORDS = "keywords"
    OUTPUT_MATCH_LEVEL = "match_level"
    OUTPUT_MATCHED_BY = "matched_by"
    OUTPUT_MESSAGE = "message"
    OUTPUT_NEW_CARD_ID = "new_card_id"
    OUTPUT_OK = "ok"
    OUTPUT_QUESTION = "question"
    OUTPUT_QUESTION_OVERLAP = "question_overlap"
    OUTPUT_RANK = "rank"
    OUTPUT_REASON = "reason"
    OUTPUT_SAME_CATEGORY = "same_category"
    OUTPUT_SCOPE = "scope"
    OUTPUT_SCORE = "score"
    OUTPUT_SEMANTIC_SCORE = "semantic_score"
    OUTPUT_SOURCE_TYPE = "source_type"
    OUTPUT_STATUS = "status"
    OUTPUT_SUMMARY = "summary"
    OUTPUT_TOTAL = "total"
    OUTPUT_UPDATED_AT = "updated_at"
    OUTPUT_WARNING = "warning"
    DUPLICATE_SCOPE_ALL = "all"
    DUPLICATE_SCOPE_TARGET = "target"
    DUPLICATE_MODE_AUTO = "auto"
    DUPLICATE_MODE_MANUAL = "manual"
    DUPLICATE_LEVEL_DUPLICATE = "duplicate"
    DUPLICATE_LEVEL_POSSIBLE = "possible_duplicate"
    MATCH_LEVEL_DISCARD = "discard"
    MATCH_LEVEL_MEDIUM = "medium"
    MATCH_LEVEL_STRONG = "strong"
    MATCH_LEVEL_WEAK = "weak"
    MATCH_SOURCE_KEYWORD = "keyword"
    MATCH_SOURCE_SEMANTIC = "semantic"
    REBUILD_STATUS_DISABLED = "disabled"
    REBUILD_STATUS_OK = "ok"
    REBUILD_STATUS_PARTIAL_FAILED = "partial_failed"
    DEFAULT_SEARCH_LIMIT = 5
    DEFAULT_RECENT_LIMIT = 10
    DEFAULT_REBUILD_LIMIT = 50
    MAX_LIMIT = 50
    OVER_FETCH_MULTIPLIER = 5
    MIN_OVER_FETCH_LIMIT = 20
    SNIPPET_LENGTH = 160
    SNIPPET_ELLIPSIS = "..."
    KEYWORD_SCORE_WEIGHT = 0.4
    SEMANTIC_SCORE_WEIGHT = 0.6
    STRONG_MATCH_THRESHOLD = 0.70
    MEDIUM_MATCH_THRESHOLD = 0.50
    WEAK_MATCH_THRESHOLD = 0.35
    DUPLICATE_SEMANTIC_WEIGHT = 0.55
    DUPLICATE_KEYWORD_OVERLAP_WEIGHT = 0.25
    DUPLICATE_QUESTION_OVERLAP_WEIGHT = 0.15
    DUPLICATE_CATEGORY_WEIGHT = 0.05
    DUPLICATE_SEMANTIC_THRESHOLD = 0.88
    DUPLICATE_SCORE_THRESHOLD = 0.82
    POSSIBLE_DUPLICATE_SCORE_THRESHOLD = 0.70
    POSSIBLE_CROSS_CATEGORY_SEMANTIC_THRESHOLD = 0.93
    POSSIBLE_DUPLICATE_KEYWORD_SCORE_THRESHOLD = 0.85
    POSSIBLE_DUPLICATE_KEYWORD_OVERLAP_THRESHOLD = 0.5
    CATEGORY_MATCH_BONUS = 1.0
    CATEGORY_MISMATCH_BONUS = 0.0
    SCORE_ROUND_DIGITS = 3
    WEAK_CANDIDATE_LIMIT = 1
    QA_KNOWLEDGE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "save_qa_card",
                "description": "保存当前用户的一条 Q&A 知识卡片。仅在用户明确提供 Q&A 并表达保存意图时使用；本工具会写入服务端事实库，并在语义索引启用时同步 pgvector 向量索引。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "用户提供的原始问题，不要改写为模型自造问题。",
                        },
                        "answer": {
                            "type": "string",
                            "description": "用户提供的原始答案，不要用模型外部知识补写。",
                        },
                        "summary": {
                            "type": "string",
                            "description": "对答案的简短摘要，用于快速浏览和检索。",
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "检索关键词，包括主题词、技术名词、项目名、工具名、API 名、模型名、数据库名、函数名或关键概念。",
                        },
                        "category": {
                            "type": "string",
                            "description": "知识卡片唯一的语义主归属分类。必须是具体稳定的短名词短语，不超过 24 个字符；不得使用其他、未分类、杂项、默认分类、未知、待分类等兜底分类；不得使用函数名、字段名、模型名、数据库名、工具名或 API 名。",
                        },
                    },
                    "required": ["question", "answer", "summary", "keywords", "category"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_qa_cards",
                "description": "使用关键词检索当前用户的 Q&A 知识卡片，作为基础检索和降级兜底。返回候选摘要，不是完整回答依据；需要回答时继续读取完整卡片。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "用户问题或检索关键词。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "最大返回数量，工具会限制到允许范围。",
                        },
                        "category": {
                            "type": "string",
                            "description": "可选硬过滤分类。只有用户明确限定分类时才传入；指定分类无结果时不要跨分类兜底。",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "hybrid_search_qa_cards",
                "description": "默认 Q&A 检索工具。用于用户要求基于当前用户个人知识库、已保存 Q&A、历史记录或来源回答时；返回候选摘要和排序信息，不是完整回答依据。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "用户问题或检索意图。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "最大返回数量，工具会限制到允许范围。",
                        },
                        "category": {
                            "type": "string",
                            "description": "可选硬过滤分类。只有用户明确限定分类时才传入；指定分类无结果时不要跨分类兜底。",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_qa_card",
                "description": "按 card_id 读取当前用户可访问的完整 Q&A 知识卡片。用于把检索、最近列表或保存结果中的真实 card_id 转换为完整回答依据。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {
                            "type": "string",
                            "description": "来自检索、最近列表或保存结果的真实 card_id。",
                        }
                    },
                    "required": ["card_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_qa_card",
                "description": "更新当前用户的一条 Q&A 知识卡片。仅当用户明确要求修改某张卡片时使用；本工具属于高风险写操作，执行前必须经过 harness 权限确认。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {
                            "type": "string",
                            "description": "要更新的卡片 ID。",
                        },
                        "question": {
                            "type": "string",
                            "description": "新的问题文本，不得用模型自造问题覆盖用户真实意图。",
                        },
                        "answer": {
                            "type": "string",
                            "description": "新的答案文本，不得用模型外部知识补写。",
                        },
                        "summary": {
                            "type": "string",
                            "description": "新的摘要，用于快速浏览和检索。",
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "新的检索关键词，包括主题词、技术名词、项目名、工具名、API 名、模型名、数据库名、函数名或关键概念。",
                        },
                        "category": {
                            "type": "string",
                            "description": "新的唯一语义主分类。必须是具体稳定的短名词短语，不超过 24 个字符；不得使用兜底分类；不得使用函数名、字段名、模型名、数据库名、工具名或 API 名。",
                        },
                    },
                    "required": ["card_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_qa_card",
                "description": "物理删除当前用户的一条 Q&A 知识卡片。仅当用户明确要求删除某张卡片时使用；本工具属于高风险写操作，执行前必须经过 harness 权限确认。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {
                            "type": "string",
                            "description": "要删除的卡片 ID。",
                        }
                    },
                    "required": ["card_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_recent_cards",
                "description": "列出当前用户最近保存的 Q&A 知识卡片。用于查看最近卡片、浏览知识库或选择要读取、更新、删除的卡片；返回摘要，不是完整回答依据。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "最大返回数量，工具会限制到允许范围。",
                        },
                        "category": {
                            "type": "string",
                            "description": "可选硬过滤分类。只有用户明确限定分类时才传入；指定分类无结果时不要跨分类兜底。",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "detect_duplicate_cards",
                "description": "检测当前用户疑似重复的 Q&A 知识卡片，只返回 duplicate 或 possible_duplicate 候选。用户主动查重、整理或合并时使用 mode=manual；保存或更新后的低打扰检测使用 mode=auto，且不得自动合并。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "enum": ["target", "all"],
                            "description": "target 检测指定卡片或文本；all 检测当前用户个人知识库全部 Q&A 卡片。",
                        },
                        "card_id": {
                            "type": "string",
                            "description": "以某张已有卡片为目标进行查重。",
                        },
                        "query": {
                            "type": "string",
                            "description": "未指定 card_id 时使用的查重查询文本。",
                        },
                        "category": {
                            "type": "string",
                            "description": "可选硬过滤分类。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "最大返回数量，工具会限制到允许范围。",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["manual", "auto"],
                            "description": "manual 表示用户主动查重；auto 表示保存或更新后的低打扰检测。",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "merge_qa_cards",
                "description": "合并当前用户的多张 Q&A 知识卡片：创建一张新卡片，并物理删除原卡片。仅当用户明确要求合并且已确认合并草案时使用；本工具属于高风险写操作，执行前必须经过 harness 权限确认。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要合并并删除的原卡片 ID，至少两张。",
                        },
                        "question": {
                            "type": "string",
                            "description": "合并后新卡片的问题，应综合原卡片且不要引入无来源内容。",
                        },
                        "answer": {
                            "type": "string",
                            "description": "合并后新卡片的答案，应综合原卡片且不要引入无来源内容。",
                        },
                        "summary": {
                            "type": "string",
                            "description": "合并后新卡片的摘要。",
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "合并后新卡片的检索关键词，包括主题词、技术名词、项目名、工具名、API 名、模型名、数据库名、函数名或关键概念。",
                        },
                        "category": {
                            "type": "string",
                            "description": "合并后新卡片的唯一语义主分类。必须是具体稳定的短名词短语，不超过 24 个字符；不得使用兜底分类；不得使用函数名、字段名、模型名、数据库名、工具名或 API 名。",
                        },
                    },
                    "required": ["card_ids", "question", "answer", "summary", "keywords", "category"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rebuild_qa_semantic_index",
                "description": "为尚未向量化的历史 Q&A 卡片重建语义向量索引。用于维护或修复语义索引，不改变 Q&A 事实内容；不是普通问答检索工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "本次最多处理的未向量化卡片数量。",
                        }
                    },
                    "additionalProperties": False,
                },
            },
        },
    ]
