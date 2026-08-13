"""What a stored diagram body states that its author did not write.

A body carries a header: the ArchiMate declarations — colours, corner shapes, glyphs, relationship
macros — and the bound on how wide a label may run. Every one of those is a rendering decision the
product makes, written into the body once and then frozen there, so a decision taken after a diagram
was last regenerated never reaches it.

Composed here rather than in the renderer because it is the whole of what "the generated header"
means, and because each half is already owned elsewhere: `ArchimateDeclarations` reads and restates
the declarations, `with_label_wrap_bound` the width. This module is the list of what the header
consists of, and the only place a new entry belongs.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations
from src.infrastructure.rendering.puml_label_wrapping import with_label_wrap_bound


def refreshed_header(body: str, repo_root: Path, config: Mapping[str, Any]) -> str:
    """*body* with everything the renderer states in it brought up to date, and nothing else.

    Every step restates what the body already carries, in place, and adds only what the body was
    written too early to have been given. An author's layout, element lines and skinparam overrides
    are none of this module's business — which is what lets a hand-laid-out diagram be brought level
    without disturbing the picture its author ruled.
    """
    body = ArchimateDeclarations.from_repo(repo_root).restated_in(body)
    return with_label_wrap_bound(body, config)
