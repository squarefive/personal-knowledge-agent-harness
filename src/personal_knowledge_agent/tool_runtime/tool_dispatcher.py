from __future__ import annotations

from typing import Any, Callable

from ..agent_tools.agent_memory_tools import AgentMemoryToolHandlers
from ..agent_tools.qa_knowledge_tools import QAKnowledgeToolHandlers
from ..agent_tools.todo_tools import TodoToolHandlers
from .constants import ToolRuntimeConstants as tool_runtime_constants
from .tool_models import ToolCall


class ToolDispatcher:
    def __init__(
        self,
        qa_tools: QAKnowledgeToolHandlers,
        memory_tools: AgentMemoryToolHandlers,
        todo_tools: TodoToolHandlers | None = None,
    ):
        self._definitions = [
            *qa_tools.definitions(),
            *(todo_tools.definitions() if todo_tools is not None else []),
            *memory_tools.definitions(),
        ]
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            tool_runtime_constants.TOOL_SAVE_QA_CARD: qa_tools.save_qa_card,
            tool_runtime_constants.TOOL_SEARCH_QA_CARDS: qa_tools.search_qa_cards,
            tool_runtime_constants.TOOL_HYBRID_SEARCH_QA_CARDS: qa_tools.hybrid_search_qa_cards,
            tool_runtime_constants.TOOL_READ_QA_CARD: qa_tools.read_qa_card,
            tool_runtime_constants.TOOL_UPDATE_QA_CARD: qa_tools.update_qa_card,
            tool_runtime_constants.TOOL_DELETE_QA_CARD: qa_tools.delete_qa_card,
            tool_runtime_constants.TOOL_LIST_RECENT_CARDS: qa_tools.list_recent_cards,
            tool_runtime_constants.TOOL_DETECT_DUPLICATE_CARDS: qa_tools.detect_duplicate_cards,
            tool_runtime_constants.TOOL_MERGE_QA_CARDS: qa_tools.merge_qa_cards,
            tool_runtime_constants.TOOL_REBUILD_QA_SEMANTIC_INDEX: qa_tools.rebuild_qa_semantic_index,
            tool_runtime_constants.TOOL_LIST_MEMORY_INDEX: memory_tools.list_memory_index,
            tool_runtime_constants.TOOL_READ_MEMORY: memory_tools.read_memory,
        }
        if todo_tools is not None:
            self._handlers.update(
                {
                    tool_runtime_constants.TOOL_CREATE_TODO: todo_tools.create_todo,
                    tool_runtime_constants.TOOL_LIST_TODOS: todo_tools.list_todos,
                    tool_runtime_constants.TOOL_UPDATE_TODO: todo_tools.update_todo,
                }
            )

    def definitions(self) -> list[dict[str, Any]]:
        return self._definitions

    def execute(self, tool_call: ToolCall) -> dict[str, Any]:
        handler = self._handlers.get(tool_call.name)
        if handler is None:
            return {
                tool_runtime_constants.RESULT_OK_FIELD: False,
                tool_runtime_constants.RESULT_ERROR_CODE_FIELD: tool_runtime_constants.ERROR_CODE_UNKNOWN_TOOL,
                tool_runtime_constants.RESULT_MESSAGE_FIELD: tool_call.name,
            }
        try:
            return handler(tool_call.arguments)
        except Exception as exc:
            return {
                tool_runtime_constants.RESULT_OK_FIELD: False,
                tool_runtime_constants.RESULT_ERROR_CODE_FIELD: tool_runtime_constants.ERROR_CODE_TOOL_ERROR,
                tool_runtime_constants.RESULT_MESSAGE_FIELD: str(exc),
            }

    def display_input(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._select(arguments, tool_runtime_constants.DISPLAY_INPUT_FIELDS.get(tool_name, ()))

    def display_output(self, tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
        return self._select(
            result,
            tool_runtime_constants.DISPLAY_OUTPUT_FIELDS.get(tool_name, tool_runtime_constants.ERROR_OUTPUT_FIELDS),
        )

    def _select(self, payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
        selected: dict[str, Any] = {}
        for field in fields:
            self._copy_field(payload, selected, field.split("."))
        return selected

    def _copy_field(self, source: Any, target: Any, parts: list[str]) -> None:
        if not parts:
            return
        head, *tail = parts
        if isinstance(source, list):
            if not isinstance(target, list):
                return
            while len(target) < len(source):
                target.append({})
            for index, item in enumerate(source):
                self._copy_field(item, target[index], parts)
            return
        if not isinstance(source, dict) or head not in source:
            return
        if not tail:
            if isinstance(target, dict):
                target[head] = source[head]
            return
        value = source[head]
        if isinstance(value, list):
            next_target = target.setdefault(head, []) if isinstance(target, dict) else []
        else:
            next_target = target.setdefault(head, {}) if isinstance(target, dict) else {}
        self._copy_field(value, next_target, tail)
