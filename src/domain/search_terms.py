"""Search synonym expansion helpers."""

from __future__ import annotations

DOMAIN_SYNONYMS: dict[str, list[str]] = {
    "policy": ["rule", "constraint", "principle", "governance"],
    "trace": ["traceability", "link", "reference", "dependency"],
    "diagram": ["puml", "visualization", "view", "model"],
    "entity": ["artifact", "model", "element", "instance"],
    "connection": ["relation", "link", "edge", "association", "realization"],
}

REVERSE_SYNONYMS: dict[str, list[str]] = {}
for _key, _values in DOMAIN_SYNONYMS.items():
    for _value in _values:
        REVERSE_SYNONYMS.setdefault(_value, []).append(_key)


def expand_tokens(tokens: list[str]) -> list[str]:
    """Return *tokens* plus one-hop synonym expansion, preserving order."""
    seen: set[str] = set(tokens)
    expanded: list[str] = list(tokens)
    for token in tokens:
        for synonym in DOMAIN_SYNONYMS.get(token, []):
            if synonym not in seen:
                expanded.append(synonym)
                seen.add(synonym)
        for synonym in REVERSE_SYNONYMS.get(token, []):
            if synonym not in seen:
                expanded.append(synonym)
                seen.add(synonym)
    return expanded
