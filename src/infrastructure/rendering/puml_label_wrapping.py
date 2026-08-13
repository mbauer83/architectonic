"""The width bound every PUML renderer owes its labels.

A PlantUML box is exactly as wide as its widest unwrapped label, and nothing in the
notation bounds that: one sentence-long label stretches its swimlane, its participant
column or its component box across the page, and every neighbour stretches with it. A
three-lane activity diagram rendered as a 4548-px landscape strip for this reason, and
bounding it took the same picture to 2037x1508 — 42% narrower — with nothing lost.

The bound is one `skinparam` pair, so the honest place for it is here rather than in
each renderer's header: a renderer that forgets it produces a diagram that is *legible*
and merely unusable at any sane zoom, which is why the omission survived so long in
several of them at once. Each type may still choose its own width through
`layout.wrap_width`, and `0` opts out for a notation whose labels are short by
construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Points of label text before PlantUML wraps onto another line. Wide enough for a short
#: sentence, narrow enough that several boxes fit a page side by side.
DEFAULT_LABEL_WRAP_WIDTH = 240


def configured_label_wrap_width(config: Mapping[str, Any], *, default: int = DEFAULT_LABEL_WRAP_WIDTH) -> int:
    """This diagram type's `layout.wrap_width`, or *default*. `0` disables wrapping."""
    layout = config.get("layout")
    configured = layout.get("wrap_width") if isinstance(layout, Mapping) else None
    return configured if isinstance(configured, int) and configured >= 0 else default


def label_wrap_skinparams(
    config: Mapping[str, Any], *, default: int = DEFAULT_LABEL_WRAP_WIDTH
) -> list[str]:
    """The header lines bounding label width, or none when the type has opted out.

    Both parameters are emitted because PlantUML splits the job between them: `wrapWidth`
    bounds the text inside a shape, `maxMessageSize` the text on an arrow. Bounding only
    the first leaves a long relationship label to widen the picture just as far.
    """
    width = configured_label_wrap_width(config, default=default)
    if width == 0:
        return []
    return [f"skinparam wrapWidth {width}", f"skinparam maxMessageSize {width}"]


#: The parameter names the bound is written with, whatever width it was written at. Stated once,
#: beside the writing, so a body already carrying the bound at a stale width is recognised as
#: carrying it rather than given a second copy — the mistake the include markers made.
_BOUND_PARAMETERS = ("wrapWidth", "maxMessageSize")


def with_label_wrap_bound(
    body: str, config: Mapping[str, Any], *, default: int = DEFAULT_LABEL_WRAP_WIDTH
) -> str:
    """*body* with this type's label width bound stated, replacing any width already stated.

    The bound is written into a body when the body is generated and then frozen there, so a diagram
    that has not been regenerated since the bound was introduced never received it. Nine ArchiMate
    diagrams here had not: their labels ran to 548px where every other diagram's stopped at 240, and
    a box wide enough to hold its label on one line is a box only one line tall.

    A type that opts out with `wrap_width: 0` states nothing, and any bound a body carries is
    removed — otherwise opting out would be something only a *new* body could do.

    A bound already stated is restated **where it stands**. Moving it to where this function would
    have written it changes nothing PlantUML reads and rewrites every body that was already
    correct: measured, 32 diagrams reported stale where 9 were.
    """
    wanted = {line.split()[1]: line for line in label_wrap_skinparams(config, default=default)}
    lines = body.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stated = next(
            (name for name in _BOUND_PARAMETERS if line.strip().startswith(f"skinparam {name} ")),
            None,
        )
        if stated is None:
            out.append(line)
        elif stated in wanted and stated not in seen:
            out.append(wanted[stated])
            seen.add(stated)
        # A duplicate, or a bound the type has opted out of, is dropped.
    missing = [line for name, line in wanted.items() if name not in seen]
    if missing:
        # Never stated before: after `@startuml`, where the renderer writes it on a new body.
        insert_at = next(
            (i + 1 for i, line in enumerate(out) if line.lstrip().startswith("@startuml")), 0
        )
        out[insert_at:insert_at] = missing
    return "\n".join(out) + ("\n" if body.endswith("\n") else "")
