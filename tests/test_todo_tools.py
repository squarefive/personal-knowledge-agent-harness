from personal_knowledge_agent.agent_context.agent_profile_memory import (
    AgentMemoryDocumentRepository,
    AgentMemoryIndexRepository,
)
from personal_knowledge_agent.agent_tools import AgentMemoryToolHandlers, QAKnowledgeToolHandlers, TodoToolHandlers
from personal_knowledge_agent.qa_data_access import QACardRepository
from personal_knowledge_agent.todo_data_access import TodoRepository
from personal_knowledge_agent.tool_runtime import ToolCall, ToolDispatcher


def create_memory_tools(tmp_path):
    return AgentMemoryToolHandlers(
        memory_index_repository=AgentMemoryIndexRepository(tmp_path),
        memory_document_repository=AgentMemoryDocumentRepository(tmp_path),
    )


def test_todo_tool_definitions_describe_usage_and_parameters(tmp_path):
    tools = TodoToolHandlers(TodoRepository(tmp_path / "knowledge.db"))
    definitions = tools.definitions()
    names = [definition["function"]["name"] for definition in definitions]

    assert names == ["create_todo", "list_todos", "update_todo"]
    for definition in definitions:
        function = definition["function"]
        parameters = function["parameters"]
        assert definition["type"] == "function"
        assert function["description"]
        assert parameters["type"] == "object"
        assert parameters["additionalProperties"] is False
        for property_schema in parameters["properties"].values():
            assert property_schema["description"]

    status_schema = definitions[1]["function"]["parameters"]["properties"]["status"]
    assert status_schema["enum"] == ["open", "done", "canceled", "all"]


def test_todo_tools_create_list_and_update(tmp_path):
    tools = TodoToolHandlers(TodoRepository(tmp_path / "knowledge.db"))

    created = tools.create_todo(
        {
            "title": "整理 todo 方案",
            "notes": "先做聊天闭环",
            "due_at": "周五",
        }
    )

    assert created["ok"] is True
    assert created["todo"]["todo_id"].startswith("todo_")
    assert created["todo"]["status"] == "open"

    listed = tools.list_todos({"query": "聊天", "status": "open"})

    assert listed["ok"] is True
    assert [todo["todo_id"] for todo in listed["todos"]] == [created["todo"]["todo_id"]]

    updated = tools.update_todo({"todo_id": created["todo"]["todo_id"], "status": "done"})

    assert updated["ok"] is True
    assert updated["todo"]["status"] == "done"
    assert tools.list_todos({})["todos"] == []
    assert tools.list_todos({"status": "all"})["todos"][0]["todo_id"] == created["todo"]["todo_id"]


def test_todo_tools_return_structured_errors(tmp_path):
    tools = TodoToolHandlers(TodoRepository(tmp_path / "knowledge.db"))

    missing_title = tools.create_todo({"notes": "缺少标题"})
    missing_todo = tools.update_todo({"todo_id": "todo_missing", "status": "done"})
    empty_patch = tools.update_todo({"todo_id": "todo_missing"})

    assert missing_title["ok"] is False
    assert missing_title["error_code"] == "invalid_input"
    assert missing_todo["ok"] is False
    assert missing_todo["error_code"] == "not_found"
    assert empty_patch["ok"] is False
    assert empty_patch["error_code"] == "invalid_input"


def test_tool_dispatcher_registers_todo_tools(tmp_path):
    qa_tools = QAKnowledgeToolHandlers(QACardRepository(tmp_path / "knowledge.db"))
    todo_tools = TodoToolHandlers(TodoRepository(tmp_path / "knowledge.db"))
    dispatcher = ToolDispatcher(qa_tools, create_memory_tools(tmp_path), todo_tools=todo_tools)

    tool_names = {
        definition["function"]["name"]
        for definition in dispatcher.definitions()
    }

    assert {"create_todo", "list_todos", "update_todo"}.issubset(tool_names)

    result = dispatcher.execute(
        ToolCall(id="call_1", name="create_todo", arguments={"title": "写 todo 测试"})
    )
    display_output = dispatcher.display_output("create_todo", result)

    assert result["ok"] is True
    assert display_output["todo"]["todo_id"].startswith("todo_")
    assert display_output["todo"]["title"] == "写 todo 测试"
