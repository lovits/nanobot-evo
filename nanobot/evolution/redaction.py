"""Bounded, JSON-safe redaction for persisted evolution evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from nanobot.evolution.constants import (
    MAX_REDACTION_DEPTH,
    MAX_REDACTION_ITEMS,
    MAX_TOOL_RESULT_CHARS,
    REDACTED_VALUE,
    TRUNCATED_SUFFIX,
)

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)
_BEARER_SECRET = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_ASSIGNMENT_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|authorization|cookie|password|secret)\s*([=:])\s*[^\s,;]+"
)
_OPENAI_STYLE_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")


def truncate_text(text: str, max_chars: int) -> str:
    """Return text capped to ``max_chars`` with a stable truncation marker."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + TRUNCATED_SUFFIX


def is_sensitive_key(key: object) -> bool:
    """Whether a mapping key denotes a value that must never be persisted."""
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_text(value: object, max_chars: int = MAX_TOOL_RESULT_CHARS) -> str:
    """Redact common inline credential forms and bound the resulting text."""
    text = str(value)
    text = _BEARER_SECRET.sub(r"\1" + REDACTED_VALUE, text)
    text = _ASSIGNMENT_SECRET.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED_VALUE}", text
    )
    text = _OPENAI_STYLE_SECRET.sub(REDACTED_VALUE, text)
    return truncate_text(text, max_chars)


def redact_value(
    value: Any,
    *,
    max_chars: int = MAX_TOOL_RESULT_CHARS,
    max_depth: int = MAX_REDACTION_DEPTH,
    max_items: int = MAX_REDACTION_ITEMS,
) -> Any:
    """Convert arbitrary tool data into a bounded, redacted JSON-safe value."""
    return _redact(value, depth=0, max_chars=max_chars, max_depth=max_depth, max_items=max_items)


def redact_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Redact tool parameters while preserving their mapping shape."""
    if not params:
        return {}
    redacted = redact_value(params)
    return redacted if isinstance(redacted, dict) else {}


def redact_tool_result(result: Any, max_chars: int = MAX_TOOL_RESULT_CHARS) -> str | None:
    """Convert a tool result, including ``ToolResult``, to a safe excerpt."""
    if result is None:
        return None
    if isinstance(result, str):
        return redact_text(result, max_chars)
    redacted = redact_value(result, max_chars=max_chars)
    return json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=_fallback_text)


def _redact(value: Any, *, depth: int, max_chars: int, max_depth: int, max_items: int) -> Any:
    if depth >= max_depth:
        return "[TRUNCATED: max depth]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return redact_text(value, max_chars)
    if isinstance(value, bytes | bytearray | memoryview):
        return "[BINARY REDACTED]"
    if isinstance(value, Enum):
        return _redact(
            value.value,
            depth=depth + 1,
            max_chars=max_chars,
            max_depth=max_depth,
            max_items=max_items,
        )
    if isinstance(value, Mapping):
        items = list(value.items())
        redacted: dict[str, Any] = {}
        for key, nested in items[:max_items]:
            key_text = redact_text(key, max_chars)
            redacted[key_text] = (
                REDACTED_VALUE
                if is_sensitive_key(key)
                else _redact(
                    nested,
                    depth=depth + 1,
                    max_chars=max_chars,
                    max_depth=max_depth,
                    max_items=max_items,
                )
            )
        if len(items) > max_items:
            redacted["[TRUNCATED: items]"] = len(items) - max_items
        return redacted
    if isinstance(value, Sequence) and not isinstance(value, str):
        values = list(value)
        redacted_values = [
            _redact(
                item, depth=depth + 1, max_chars=max_chars, max_depth=max_depth, max_items=max_items
            )
            for item in values[:max_items]
        ]
        if len(values) > max_items:
            redacted_values.append("[TRUNCATED: items]")
        return redacted_values
    return f"[UNSERIALIZABLE: {type(value).__name__}]"


def _fallback_text(value: object) -> str:
    return f"[UNSERIALIZABLE: {type(value).__name__}]"
