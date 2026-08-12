"""How a PlantUML arrow token is decorated — one reading and one writing, for every caller.

An arrow token is the middle of a connection line: `-->`, `..>`, `--|>`, `-[#red]->`, `o--`. Two
things get inserted into one, and both have to know where the *line* of the arrow starts, because
that is the only place PlantUML accepts them:

* a **direction** — `-->` becomes `-down->`, so GraphViz ranks the target below the source;
* a **line style** — `-->` becomes `-[dashed]->`.

There were **three** implementations of the direction insert: the renderer's, the layout
optimiser's that rewrites stored bodies, and a third in `diagram_builder` that no caller had
reached since it was copied. The two live ones agreed, which is the dangerous kind of duplicate:
nothing failed, so nothing said they were both there, and a token form taught to one would simply
be missing from the other. That is not hypothetical — adding the containment arrows (`o--`, `*--`)
required exactly such a form, and a fix applied to the renderer alone would have left the layout
optimiser silently dropping the direction from every arrow it rewrote.

**The token's shape, as these functions understand it.** An optional source marker (`o`, `*`),
then the line (`-` or `.`), then the rest. The marker is what ArchiMate containment needs: PlantUML
draws a hollow diamond for `o--` and a filled one for `*--`, at the *source* end — and its
directional form puts the direction inside the line, after the marker: `o-down-`.
"""

from __future__ import annotations

import re

#: A direction already present, or a link that must not be redirected at all.
_ALREADY_DIRECTED = re.compile(r"(up|down|left|right)")

#: The optional end marker a token may open with, before its line begins.
_SOURCE_MARKER = re.compile(r"^(?P<marker>[o*]?)(?P<line>[-.])(?P<rest>.*)$")


def insert_arrow_direction(arrow: str, direction: str) -> str:
    """Insert a direction hint into *arrow*, or return it unchanged where none can go.

    Unchanged for a hidden link (its direction is already the caller's own business), for a token
    that states a direction already, and for anything this does not recognise as an arrow.
    """
    if "[hidden]" in arrow or _ALREADY_DIRECTED.search(arrow):
        return arrow
    # Bracket syntax states the line's decoration explicitly: `-[#red]->` → `-[#red]down->`.
    if bracketed := re.match(r"(.*\])(.+)", arrow):
        return bracketed.group(1) + direction + bracketed.group(2)
    match = _SOURCE_MARKER.match(arrow)
    if match is None:
        return arrow
    marker, line, rest = match.group("marker", "line", "rest")
    # The direction sits inside the line, and the line must still read as one: `-->` → `-down->`
    # keeps its two dashes, while `-|>` → `-down-|>` has to grow the one it would have lost.
    separator = "" if rest.startswith(line) else line
    return f"{marker}{line}{direction}{separator}{rest}"


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
    match = _SOURCE_MARKER.match(arrow)
    if match is None:
        return arrow
    marker, line, rest = match.group("marker", "line", "rest")
    return f"{marker}{line}[{line_style}]{rest}"
