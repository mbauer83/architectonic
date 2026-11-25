"""Rewrite one top-level key's block of a frontmatter's YAML text, every other line left as it was.

Steps that change a field or two of a file written by an earlier release go through these, so the
rest of the file — fields the step has no opinion about, their order, an uncommitted edit — keeps every
byte. Re-dumping the whole mapping would be simpler and would reorder it.
"""

from __future__ import annotations

import yaml  # type: ignore[import-untyped]


def block_span(lines: list[str], key: str) -> tuple[int, int] | None:
    """The lines a top-level frontmatter key and its value occupy, as ``[start, end)``."""
    start = next((index for index, line in enumerate(lines) if line.startswith(f"{key}:")), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][0] in " -"):
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1  # blank lines after the block are not the block's
    return start, end


def with_block(text: str, key: str, value: object) -> str:
    """*text* with the block of top-level *key* re-dumped from *value*; unchanged where there is none."""
    lines = text.split("\n")
    span = block_span(lines, key)
    if span is None:
        return text
    dumped = str(yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True)).rstrip("\n").split("\n")
    return "\n".join([*lines[: span[0]], *dumped, *lines[span[1]:]])


def without_block(text: str, key: str) -> str:
    """*text* without the block of top-level *key*."""
    lines = text.split("\n")
    span = block_span(lines, key)
    return text if span is None else "\n".join([*lines[: span[0]], *lines[span[1]:]])


def renamed_block(text: str, key: str, renamed: str) -> str:
    """*text* with top-level *key* called *renamed*, its value as written."""
    lines = text.split("\n")
    span = block_span(lines, key)
    if span is None:
        return text
    lines[span[0]] = renamed + lines[span[0]][len(key):]
    return "\n".join(lines)
