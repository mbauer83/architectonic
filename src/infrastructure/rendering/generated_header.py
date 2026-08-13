"""What a stored diagram body states that its author did not write.

A body carries a header: the ArchiMate declarations — colours, corner shapes, glyphs, relationship
macros — and the skinparams the renderer states about labels, their width bound and their alignment.
Every one of those is a rendering decision the product makes, written into the body once and then
frozen there, so a decision taken after a diagram was last regenerated never reaches it.

Composed here rather than in the renderer because it is the whole of what "the generated header"
means, and because each half is already owned elsewhere: `ArchimateDeclarations` reads and restates
the declarations, `label_wrap_skinparams` says what the width bound is. This module is the list of
what the header consists of, and the only place a new entry belongs.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations
from src.infrastructure.rendering.puml_label_wrapping import label_wrap_skinparams

#: How a label's lines sit against each other. A box's label is one string — the glyph, then the
#: text — so a label that wraps puts its continuation, and the `«specialization»` line after it,
#: hard against the left edge under the glyph while the first line spans the full width. Centred,
#: every line reads against the same axis. Stated for the ArchiMate family only: the other notations
#: emit their own headers and a participant column or a C4 description aligns by its own convention.
_TEXT_ALIGNMENT = "skinparam defaultTextAlignment center"


def refreshed_header(body: str, repo_root: Path, config: Mapping[str, Any]) -> str:
    """*body* with everything the renderer states in it brought up to date, and nothing else.

    Every step restates what the body already carries, in place, and adds only what the body was
    written too early to have been given. An author's layout, element lines and skinparam overrides
    are none of this module's business — which is what lets a hand-laid-out diagram be brought level
    without disturbing the picture its author ruled.
    """
    body = ArchimateDeclarations.from_repo(repo_root).restated_in(body)
    stated = {line.split()[1]: line for line in label_wrap_skinparams(config)}
    stated[_TEXT_ALIGNMENT.split()[1]] = _TEXT_ALIGNMENT
    return with_stated_skinparams(body, stated)


def with_stated_skinparams(body: str, wanted: Mapping[str, str]) -> str:
    """*body* with each named skinparam stated as *wanted* says, restated **where it stands**.

    Moving one to where a freshly generated body would carry it changes nothing PlantUML reads and
    rewrites every body that was already correct: measured, 32 diagrams reported stale where 9 were.

    A name absent from *wanted* is a statement the renderer no longer makes, so a copy the body
    carries is dropped — otherwise withdrawing one would be something only a new body could do.
    """
    out: list[str] = []
    seen: set[str] = set()
    for line in body.splitlines():
        stated = _stated_parameter(line)
        if stated is None:
            out.append(line)
        elif stated in wanted and stated not in seen:
            out.append(wanted[stated])
            seen.add(stated)
        # A duplicate, or one the renderer no longer states, is dropped.
    missing = [line for name, line in wanted.items() if name not in seen]
    if missing:
        # Never stated before: after `@startuml`, where a new body carries it.
        insert_at = next(
            (i + 1 for i, line in enumerate(out) if line.lstrip().startswith("@startuml")), 0
        )
        out[insert_at:insert_at] = missing
    return "\n".join(out) + ("\n" if body.endswith("\n") else "")


#: Every parameter this module states, whatever value it was written with. A body carrying one at a
#: superseded value has to be recognised as carrying it rather than given a second copy.
_STATED_PARAMETERS = ("wrapWidth", "maxMessageSize", "defaultTextAlignment")


def _stated_parameter(line: str) -> str | None:
    stripped = line.strip()
    return next(
        (name for name in _STATED_PARAMETERS if stripped.startswith(f"skinparam {name} ")), None
    )
