"""A diagram's purpose line in the shape its read serves: the lists it states, and the line it shows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from src.application.viewpoints.diagram_purpose import diagram_purpose
from src.domain.purpose_lines import (
    MalformedPurposeLine,
    Prose,
    PurposeEntry,
    purpose_lines_as_written,
    read_purpose_lines,
)
from src.domain.viewpoints.viewpoints import ViewpointCatalog

#: The name of the element an id refers to, or None where the repository holds none.
type NameOf = Callable[[str], str | None]


def _shown(entry: PurposeEntry, name_of: NameOf) -> dict[str, str]:
    match entry:
        case Prose(text):
            return {"text": text}
        case _:
            return {"text": name_of(entry.artifact_id) or entry.artifact_id, "ref": entry.artifact_id}


def purpose_read(frontmatter: Mapping[str, object], viewpoints: ViewpointCatalog, name_of: NameOf) -> dict[str, Any]:
    """`stakeholders`/`concerns` as the diagram states them (what an editor sends back) and `purpose`, shown.

    `purpose` is absent where neither the diagram nor its viewpoint states anything; a stored value that
    cannot be read is served as stating nothing, and the verifier says why.
    """
    try:
        own = purpose_lines_as_written(read_purpose_lines(frontmatter))
    except MalformedPurposeLine:
        own = {}
    purpose = diagram_purpose(frontmatter, viewpoints)
    if purpose.lines.is_empty:
        return dict(own)
    return {
        **own,
        "purpose": {
            "stakeholders": [_shown(entry, name_of) for entry in purpose.lines.stakeholders],
            "concerns": [_shown(entry, name_of) for entry in purpose.lines.concerns],
            "inherited_from": purpose.inherited_from,
        },
    }
