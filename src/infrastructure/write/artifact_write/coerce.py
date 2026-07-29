from __future__ import annotations

from typing import Any


def as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def as_optional_str_list(value: object) -> list[str] | None:
    if value is None or not isinstance(value, list):
        return None
    return [str(item) for item in value]


def as_optional_str_dict(value: object) -> dict[str, str] | None:
    if value is None or not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


def as_optional_typed_dict(value: object) -> dict[str, Any] | None:
    """Convert an incoming properties dict to typed values (preserves non-string scalars).

    Unlike ``as_optional_str_dict``, this does NOT call ``str()`` on values —
    typed values (int, float, bool, list) pass through so the formatter can
    encode them using the canonical lexical codec.  String values pass through
    as-is.  Non-dict inputs return ``None``.
    """
    if value is None or not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}
