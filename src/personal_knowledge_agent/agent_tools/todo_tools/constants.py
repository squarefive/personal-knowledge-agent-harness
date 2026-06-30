from typing import Any

class TodoToolConstants:
    FIELD_OK = "ok"
    FIELD_ERROR_CODE = "error_code"
    FIELD_MESSAGE = "message"
    FIELD_TODO = "todo"
    FIELD_TODOS = "todos"
    FIELD_TODO_ID = "todo_id"
    TODO_MODEL_ID_FIELD = "id"

    ARG_TITLE = "title"
    ARG_NOTES = "notes"
    ARG_DUE_AT = "due_at"
    ARG_QUERY = "query"
    ARG_STATUS = "status"
    ARG_LIMIT = "limit"
    ARG_TODO_ID = "todo_id"

    PATCH_TITLE = "title"
    PATCH_NOTES = "notes"
    PATCH_STATUS = "status"
    PATCH_DUE_AT = "due_at"
    PATCH_CLEAR_DUE_AT = "clear_due_at"

    ERROR_INVALID_INPUT = "invalid_input"
    ERROR_NOT_FOUND = "not_found"

    STATUS_OPEN = "open"
    STATUS_DONE = "done"
    STATUS_CANCELED = "canceled"
    STATUS_ALL = "all"
    UPDATE_STATUS_VALUES = [STATUS_OPEN, STATUS_DONE, STATUS_CANCELED]
    LIST_STATUS_VALUES = [STATUS_OPEN, STATUS_DONE, STATUS_CANCELED, STATUS_ALL]

    DEFAULT_STATUS = STATUS_OPEN
    DEFAULT_LIMIT = 20
    MAX_LIMIT = 50
    TODO_TOOL_DEFINITIONS: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "create_todo",
                "description": "保存当前用户的一条 todo 待办项。当用户明确要求记录之后要做的行动项、任务或待办时使用；本工具会写入服务端事实库。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        ARG_TITLE: {
                            "type": "string",
                            "description": "待办标题，应是用户要之后执行的具体行动项；不得把普通聊天、假设或未确认计划保存为待办。",
                        },
                        ARG_NOTES: {
                            "type": "string",
                            "description": "可选补充说明。只有用户提供额外背景或细节时填写；没有则省略。",
                        },
                        ARG_DUE_AT: {
                            "type": "string",
                            "description": "可选截止时间。第一版只保存用户明确提供的时间文本或 ISO 风格字符串，不做提醒或自然语言时间推断。",
                        },
                    },
                    "required": [ARG_TITLE],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_todos",
                "description": "查询当前用户 todo 待办项。当用户要求查看、搜索或核对当前用户 todo 列表时使用；默认只返回 open 待办。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        ARG_QUERY: {
                            "type": "string",
                            "description": "可选搜索词，用于匹配待办标题和备注。",
                        },
                        ARG_STATUS: {
                            "type": "string",
                            "enum": LIST_STATUS_VALUES,
                            "description": "可选状态过滤。默认 open；用户明确要求全部时使用 all；用户要求已完成或已取消时分别使用 done 或 canceled。",
                        },
                        ARG_LIMIT: {
                            "type": "integer",
                            "description": "最大返回数量，工具会限制到允许范围。",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_todo",
                "description": "更新当前用户的一条 todo 待办项。当用户明确要求修改待办标题、备注、截止时间或状态时使用；需要真实 todo_id。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        ARG_TODO_ID: {
                            "type": "string",
                            "description": "要更新的 todo ID。若用户没有提供明确 ID，应先查询候选并让用户确认，不要凭最近一条待办静默修改。",
                        },
                        ARG_TITLE: {
                            "type": "string",
                            "description": "新的待办标题，提供时必须是非空具体行动项。",
                        },
                        ARG_NOTES: {
                            "type": "string",
                            "description": "新的补充说明。可为空字符串，用于清空备注。",
                        },
                        ARG_STATUS: {
                            "type": "string",
                            "enum": UPDATE_STATUS_VALUES,
                            "description": "新的待办状态。完成使用 done；取消或不再需要使用 canceled；重新打开使用 open。",
                        },
                        ARG_DUE_AT: {
                            "type": "string",
                            "description": "新的截止时间。空字符串表示清空截止时间；第一版不做提醒或自然语言时间推断。",
                        },
                    },
                    "required": [ARG_TODO_ID],
                    "additionalProperties": False,
                },
            },
        },
    ]
