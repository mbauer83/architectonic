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
