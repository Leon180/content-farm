"""stream-json events whose ``message`` is a plain string (e.g. system notices) must not crash the trace."""

from __future__ import annotations

from content_farm.review.trace import rows_of


def test_an_event_with_a_string_message_yields_no_rows():
    assert rows_of({"type": "assistant", "message": "api retry"}, 1.0) == []
    assert rows_of({"type": "user", "message": None}, 1.0) == []


def test_an_assistant_event_still_yields_model_and_tool_rows():
    event = {"type": "assistant", "message": {"usage": {"output_tokens": 5}, "content": [
        {"type": "text"}, {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a.md"}}]}}
    kinds = [row[1] for row in rows_of(event, 2.0)]
    assert kinds == ["model", "tool_use"]
