from __future__ import annotations

import re


def pluralize_label(label: str) -> str:
    words = label.split()
    if not words:
        return label
    last = words[-1]
    lower = last.lower()
    if lower.endswith(("s", "x", "z")) or lower.endswith(("ch", "sh")):
        last = last + "es"
    elif lower.endswith("y") and (len(lower) == 1 or lower[-2] not in "aeiou"):
        last = last[:-1] + "ies"
    else:
        last = last + "s"
    words[-1] = last
    return " ".join(words)


def insert_arrow_line_style(arrow: str, line_style: str) -> str:
    """Insert a PlantUML line-style modifier (e.g. ``dashed``, ``dotted``) into a plain arrow
    token, e.g. ``-->`` -> ``-[dashed]->``.

    Skipped (returns *arrow* unchanged) when it already carries a bracket or a direction
    word — merging a line style with a pre-existing direction hint correctly needs the
    style and direction combined inside one bracket (``-[dashed,down]->``), which no real
    specialization exercises today; callers apply direction hints and line styles as
    mutually exclusive on one connection rather than risk a malformed merge.
    """
    if not line_style or "[" in arrow or re.search(r"(up|down|left|right|hidden)", arrow):
        return arrow
    if arrow.startswith((".", "-")):
        return arrow[0] + f"[{line_style}]" + arrow[1:]
    return arrow


def insert_arrow_direction(arrow: str, direction: str) -> str:
    if "[hidden]" in arrow or re.search(r"(up|down|left|right)", arrow):
        return arrow
    match = re.match(r"(.*\])(.+)", arrow)
    if match:
        return match.group(1) + direction + match.group(2)
    if arrow.startswith("."):
        return "." + direction + arrow[1:]
    if arrow.startswith("-"):
        rest = arrow[1:]
        sep = "" if rest.startswith("-") else "-"
        return "-" + direction + sep + rest
    return arrow
