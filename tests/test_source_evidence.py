import json

from personal_knowledge_agent.agent_loop.source_evidence import extract_sources, finalize_answer


def assistant_tool_call(tool_call_id, name, arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    }


def tool_result(tool_call_id, result):
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


def test_extract_sources_from_save_qa_card_uses_arguments_for_question():
    messages = [
        {"role": "user", "content": "帮我记一条知识"},
        assistant_tool_call(
            "call_1",
            "save_qa_card",
            {
                "question": "什么是最小闭环？",
                "answer": "能保存、检索、回答并引用来源。",
                "summary": "最小闭环包含保存、检索、回答和来源。",
                "keywords": ["最小闭环"],
            },
        ),
        tool_result(
            "call_1",
            {
                "ok": True,
                "card_id": "qa_1",
                "source_type": "manual_qa",
                "created_at": "2026-06-07T00:00:00+00:00",
            },
        ),
    ]

    sources = extract_sources(messages)

    assert len(sources) == 1
    assert sources[0].card_id == "qa_1"
    assert sources[0].question == "什么是最小闭环？"
    assert sources[0].evidence_kind == "saved"


def test_finalize_answer_replaces_model_source_section_with_trusted_sources():
    messages = [
        assistant_tool_call("call_1", "search_qa_cards", {"query": "最小闭环"}),
        tool_result(
            "call_1",
            {
                "ok": True,
                "cards": [
                    {
                        "card_id": "qa_1",
                        "question": "什么是最小闭环？",
                        "summary": "最小闭环包含保存、检索、回答和来源。",
                        "answer_snippet": "能保存、检索、回答并引用来源。",
                        "score": 4,
                        "source_type": "manual_qa",
                        "created_at": "2026-06-07T00:00:00+00:00",
                    }
                ],
            },
        ),
    ]

    trusted = finalize_answer("回答正文。\n\n来源：\n- card_id: qa_fake", messages)

    assert trusted.source_count == 1
    assert trusted.removed_model_sources is True
    assert "qa_fake" not in trusted.answer
    assert "card_id: qa_1" in trusted.answer
    assert "原始问题: 什么是最小闭环？" in trusted.answer


def test_extract_sources_from_list_recent_cards_result():
    messages = [
        assistant_tool_call("call_1", "list_recent_cards", {"limit": 50}),
        tool_result(
            "call_1",
            {
                "ok": True,
                "cards": [
                    {
                        "card_id": "qa_1",
                        "question": "什么是skills",
                        "summary": "Skills 是通过学习掌握的能力。",
                        "source_type": "manual_qa",
                        "created_at": "2026-06-13T09:12:28+00:00",
                    }
                ],
            },
        ),
    ]

    sources = extract_sources(messages)

    assert len(sources) == 1
    assert sources[0].card_id == "qa_1"
    assert sources[0].question == "什么是skills"
    assert sources[0].evidence_kind == "searched"


def test_hybrid_search_and_read_same_card_are_counted_once():
    messages = [
        assistant_tool_call("call_1", "hybrid_search_qa_cards", {"query": "skills", "limit": 3}),
        tool_result(
            "call_1",
            {
                "ok": True,
                "cards": [
                    {
                        "card_id": "qa_1",
                        "question": "什么是skills",
                        "summary": "Skills 是通过学习掌握的能力。",
                        "answer_snippet": "Skills 是通过学习掌握的能力。",
                        "source_type": "manual_qa",
                        "created_at": "2026-06-13T09:12:28+00:00",
                    }
                ],
            },
        ),
        assistant_tool_call("call_2", "read_qa_card", {"card_id": "qa_1"}),
        tool_result(
            "call_2",
            {
                "ok": True,
                "card": {
                    "card_id": "qa_1",
                    "question": "什么是skills",
                    "answer": "Skills 是通过学习掌握的能力。",
                    "summary": "Skills 是通过学习掌握的能力。",
                    "source_type": "manual_qa",
                    "created_at": "2026-06-13T09:12:28+00:00",
                },
            },
        ),
    ]

    trusted = finalize_answer("回答正文。", messages)

    assert trusted.source_count == 1
    assert trusted.answer.count("card_id: qa_1") == 1


def test_finalize_answer_does_not_use_previous_turn_messages():
    previous_turn = [
        assistant_tool_call("call_1", "search_qa_cards", {"query": "最小闭环"}),
        tool_result(
            "call_1",
            {
                "ok": True,
                "cards": [
                    {
                        "card_id": "qa_1",
                        "question": "什么是最小闭环？",
                        "summary": "最小闭环包含保存、检索、回答和来源。",
                        "answer_snippet": "能保存、检索、回答并引用来源。",
                        "score": 4,
                        "source_type": "manual_qa",
                        "created_at": "2026-06-07T00:00:00+00:00",
                    }
                ],
            },
        ),
    ]
    current_turn = [{"role": "user", "content": "Python list 怎么去重？"}]

    trusted = finalize_answer("可以用 set 去重。", current_turn)

    assert trusted.source_count == 0
    assert "qa_1" not in trusted.answer
    assert extract_sources(previous_turn)


def test_finalize_answer_removes_unsupported_local_kb_claim_without_sources():
    trusted = finalize_answer("根据本地知识库，可以这样做。\ncard_id: qa_fake", [])

    assert trusted.source_count == 0
    assert trusted.removed_unsupported_claim is True
    assert "本地知识库" not in trusted.answer
    assert "qa_fake" not in trusted.answer


def test_empty_search_and_failed_tool_result_are_not_sources():
    messages = [
        assistant_tool_call("call_1", "search_qa_cards", {"query": "未知"}),
        tool_result("call_1", {"ok": True, "cards": []}),
        assistant_tool_call("call_2", "read_qa_card", {"card_id": "qa_missing"}),
        tool_result("call_2", {"ok": False, "error_code": "not_found", "message": "missing"}),
    ]

    trusted = finalize_answer("没有找到足够依据。", messages)

    assert trusted.source_count == 0
    assert "来源：" not in trusted.answer
