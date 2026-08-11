from __future__ import annotations

from nanobot.agent.tools.base import ToolResult
from nanobot.evolution.constants import REDACTED_VALUE
from nanobot.evolution.redaction import redact_params, redact_text, redact_tool_result, redact_value


def test_redacts_sensitive_keys_recursively() -> None:
    result = redact_params(
        {
            "api_key": "secret",
            "nested": [{"Authorization": "Bearer hidden"}, {"safe": "visible"}],
            "cookie": "session=secret",
        }
    )

    assert result["api_key"] == REDACTED_VALUE
    assert result["nested"][0]["Authorization"] == REDACTED_VALUE
    assert result["nested"][1]["safe"] == "visible"
    assert result["cookie"] == REDACTED_VALUE


def test_redacts_inline_secrets_and_truncates() -> None:
    assert "hidden" not in redact_text("Authorization: Bearer hidden")
    assert "sk-" not in redact_text("provider rejected sk-exampleCredential123456789")
    assert redact_text("abcdef", 3).endswith("(truncated)")


def test_bounds_depth_and_converts_non_json_values() -> None:
    value = {"one": {"two": {"three": "value"}}}
    assert "max depth" in str(redact_value(value, max_depth=2))
    assert redact_value({"payload": b"raw"}) == {"payload": "[BINARY REDACTED]"}
    assert "object at" not in str(redact_value({"thing": object()}))


def test_tool_results_are_safe_text() -> None:
    assert redact_tool_result(ToolResult.error("token=secret")) == "token=[REDACTED]"
    assert redact_tool_result(None) is None
