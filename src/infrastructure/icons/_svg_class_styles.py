"""The class rules of an SVG's `<style>` elements, as declarations to inline.

Illustrator and similar exporters colour a logo through `<style>` rules such as `.cls-1{fill:#0078d4}`
and `class="cls-1"` on each shape. The sanitised document carries no `<style>` element — a stylesheet
can load a file or URL through `@import` and `url()` — so without this reading such a logo is
drawn black. Only rules whose selectors are all plain class names are read; every other rule, and
every at-rule, is ignored, and each declaration later passes the same property allow-list an inline
`style` attribute does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}")
_CLASS_SELECTOR_RE = re.compile(r"^\.([A-Za-z_][\w-]*)$")


def class_declarations(stylesheets: Iterable[str]) -> Mapping[str, str]:
    """Class name to its declarations, later rules appended after earlier ones as CSS orders them."""
    by_class: dict[str, list[str]] = {}
    for sheet in stylesheets:
        text = _COMMENT_RE.sub("", sheet)
        if "@" in text:
            text = _without_at_rules(text)
        for selectors, body in _RULE_RE.findall(text):
            names = [_CLASS_SELECTOR_RE.match(s.strip()) for s in selectors.split(",")]
            if all(names):
                for match in names:
                    if match is not None:
                        by_class.setdefault(match.group(1), []).append(body.strip())
    return {name: ";".join(bodies) for name, bodies in by_class.items()}


def _without_at_rules(text: str) -> str:
    """Drop every at-rule, block or statement, so none of its content is read as a class rule."""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "@":
            i = _at_rule_end(text, i)
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _at_rule_end(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == ";" and depth == 0:
            return index + 1
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(text)
