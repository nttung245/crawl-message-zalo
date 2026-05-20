from __future__ import annotations

import json

from app.modules.linkedin.utils.post_reaction_webhook_ack import (
    evaluate_post_reaction_webhook_response,
    truthy_success_value,
)


def test_truthy_success_string_and_bool() -> None:
    assert truthy_success_value("true") is True
    assert truthy_success_value("TRUE") is True
    assert truthy_success_value("false") is False
    assert truthy_success_value(True) is True
    assert truthy_success_value(1) is True


def test_eval_http_error() -> None:
    ok, msg = evaluate_post_reaction_webhook_response(500, '{"success":"true"}')
    assert ok is False
    assert "500" in msg


def test_eval_success_root_string() -> None:
    ok, msg = evaluate_post_reaction_webhook_response(
        200,
        json.dumps({"success": "true"}),
    )
    assert ok is True
    assert msg == ""


def test_eval_success_nested_body() -> None:
    ok, msg = evaluate_post_reaction_webhook_response(
        200,
        json.dumps({"body": {"success": True}}),
    )
    assert ok is True


def test_eval_success_false_fails() -> None:
    ok, msg = evaluate_post_reaction_webhook_response(
        200,
        json.dumps({"success": "false"}),
    )
    assert ok is False
    assert "success" in msg.lower()


def test_eval_non_json_ok() -> None:
    ok, msg = evaluate_post_reaction_webhook_response(200, "OK")
    assert ok is True
