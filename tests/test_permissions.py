from personal_knowledge_agent.permissions import (
    ApprovalRequest,
    check_permission,
    default_approval_callback,
    permission_denied_result,
)


def test_safe_tools_are_allowed():
    decision = check_permission("search_qa_cards", {"query": "本地"})

    assert decision.behavior == "allow"


def test_update_and_delete_tools_require_approval():
    update_decision = check_permission("update_qa_card", {"card_id": "qa_1"})
    delete_decision = check_permission("delete_qa_card", {"card_id": "qa_1"})
    merge_decision = check_permission("merge_qa_cards", {"card_ids": ["qa_1", "qa_2"]})

    assert update_decision.behavior == "ask"
    assert delete_decision.behavior == "ask"
    assert merge_decision.behavior == "ask"
    assert update_decision.reason


def test_default_approval_callback_denies():
    request = ApprovalRequest(tool_name="delete_qa_card", arguments={"card_id": "qa_1"}, reason="danger")

    assert default_approval_callback(request) is False


def test_permission_denied_result_is_structured():
    result = permission_denied_result("Permission denied by user.")

    assert result == {
        "ok": False,
        "error_code": "permission_denied",
        "message": "Permission denied by user.",
    }
