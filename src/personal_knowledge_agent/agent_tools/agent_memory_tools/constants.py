from typing import Any

class AgentMemoryToolConstants:
    FIELD_OK = "ok"
    FIELD_ERROR_CODE = "error_code"
    FIELD_MESSAGE = "message"
    FIELD_ENTRIES = "entries"
    FIELD_MEMORY = "memory"

    ARG_LIMIT = "limit"
    ARG_NAME = "name"

    ERROR_INVALID_MEMORY_INDEX = "invalid_memory_index"
    ERROR_INVALID_MEMORY = "invalid_memory"
    ERROR_NOT_FOUND = "not_found"

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 50
    AGENT_MEMORY_TOOL_DEFINITIONS: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "list_memory_index",
                "description": "列出 Agent memory 索引。Agent memory 只用于理解用户偏好、项目约束和协作上下文，不能作为 Q&A 知识库事实来源。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        ARG_LIMIT: {
                            "type": "integer",
                            "description": "最大返回数量，工具会限制到允许范围。",
                        }
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_memory",
                "description": "按 memory name 读取 Agent memory 全文。仅用于理解用户偏好、项目约束和协作上下文；不得把 memory 内容作为 Q&A 卡片来源或当前用户个人知识库事实依据。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        ARG_NAME: {
                            "type": "string",
                            "description": "来自 memory index 的 memory name。",
                        }
                    },
                    "required": [ARG_NAME],
                    "additionalProperties": False,
                },
            },
        },
    ]
