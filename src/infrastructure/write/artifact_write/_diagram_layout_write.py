"""What a diagram write does with a layout and with its groupings' identities, for create and edit alike.

A layout arrives whole or not at all: a caller passes the block it wants stored, an empty one to
return the diagram to PlantUML's arrangement, or nothing to keep what is there. Three things are
decided here, once, so the two write functions cannot answer differently:

* **Whether the diagram may carry one.** A diagram is either ``manual-layout`` — a hand-written body
  kept verbatim — or laid out, never both; and only a diagram drawn from the model takes a layout,
  because one that holds its own records is drawn by another generator.
* **What a stated block may name.** A caller stating geometry for something the diagram does not
  hold is refused, with what and where.
* **What becomes of a stored block when the diagram shrinks.** An edit that removes a member, a
  grouping or a relation takes their geometry with it, in the same write, and says so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from src.application.modeling.diagram_identities import diagram_identities
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.domain.diagrams.authored_groupings import (
    NOT_YET_UPGRADED,
    check_groupings,
    stored_before_groupings_had_ids,
    with_grouping_ids,
)
from src.domain.diagrams.layout.layout_block import layout_as_written, read_layout
from src.domain.diagrams.layout.layout_checks import EntriesNamingNothing, pruned_to

from .diagram_references import diagram_entities_are_authoritative
from .types import SyncDiagramToModelResult

NEITHER_BOTH = (
    "A diagram is either manual-layout, whose hand-written body is kept verbatim, or laid out, never "
    "both. Pass layout={} to remove the layout, or manual_layout=false to let the body be generated."
)


def identified_groupings(
    stated: Sequence[dict[str, object]] | None, *, diagram_id: str, stored: object = None
) -> list[dict[str, object]] | None:
    """The groupings a caller stated, each with a stable id; refused where an entry is not a grouping.

    An entry arriving without an id is new, and is given one here. One arriving with its id keeps it,
    which is how an editor rewriting the whole list keeps each box's layout attached to it.

    *stored* is what the diagram's file holds. Where that is the earlier format — a grouping with no
    id — the edit is refused whatever it states: minting here would convert stored content behind
    the upgrade's back, and a caller sending back what it read is indistinguishable from one stating
    something new.
    """
    if stored_before_groupings_had_ids(stored):
        raise ValueError(NOT_YET_UPGRADED)
    if stated is None:
        return None
    identified = with_grouping_ids(stated, diagram_id=stable_id(diagram_id))
    if problems := check_groupings(identified):
        raise ValueError(" ".join(problems))
    return identified


def _named(dangling: EntriesNamingNothing) -> str:
    parts = [
        f"{kind} {', '.join(keys)}"
        for kind, keys in (
            ("element", dangling.elements), ("box", dangling.boxes),
            ("relation", dangling.relations), ("stacked entry", dangling.stacked),
        )
        if keys
    ]
    return "; ".join(parts)


def layout_for_write(
    *,
    stated: Mapping[str, object] | None,
    stored: object,
    manual_layout: bool,
    verifier: ArtifactVerifier,
    diagram_type: str,
    warnings: list[str],
    entity_ids_used: Sequence[str] | None,
    connection_ids_used: Sequence[str] | None,
    diagram_entities: object,
    diagram_connections: object,
    authored_groupings: object,
    bindings: object,
) -> dict[str, object] | None:
    """The layout block this write stores, or None for none.

    *stated* is the caller's whole block (empty to remove it); *stored* what the file holds, used
    when the caller says nothing. The rest is what the diagram will hold once written. Entries of a
    stored block that name what the diagram no longer holds are dropped and reported in *warnings*;
    the same in a stated block is refused.
    """
    chosen = stated if stated is not None else stored
    if not isinstance(chosen, Mapping) or not chosen:
        return None
    layout = read_layout(chosen)
    if manual_layout:
        raise ValueError(NEITHER_BOTH)
    if diagram_entities_are_authoritative(verifier, diagram_type):
        raise ValueError(
            "Only a diagram drawn from the model takes a layout; this diagram type holds its own "
            "records and is arranged by its own generator."
        )
    kept, dangling = pruned_to(
        layout,
        diagram_identities(
            entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
            diagram_entities=diagram_entities, diagram_connections=diagram_connections,
            authored_groupings=authored_groupings, bindings=bindings,
        ),
    )
    dropped = EntriesNamingNothing(dangling.elements, dangling.boxes, (), dangling.relations, dangling.stacked)
    if dropped.any() and stated is not None:
        raise ValueError(f"The layout names what this diagram does not hold: {_named(dropped)}.")
    if dropped.any():
        warnings.append(f"Dropped from the layout, as the diagram no longer holds them: {_named(dropped)}.")
    return layout_as_written(kept) or None


def left_for_the_upgrade(
    frontmatter: Mapping[str, object], diagram_path: Path, artifact_id: str
) -> SyncDiagramToModelResult | None:
    """A sync's answer for a diagram stored in the earlier grouping format, or None where it is current.

    A sync rewrites the diagram and would have to store its groupings: keeping them is storing the
    earlier format again, and giving them ids is the upgrade's change to make. So the diagram is
    left exactly as it is, and the result says why and what to run.
    """
    if not stored_before_groupings_had_ids(frontmatter.get("authored-groupings")):
        return None
    return SyncDiagramToModelResult(
        wrote=False, path=diagram_path, artifact_id=artifact_id, content=None,
        warnings=[f"Not synchronised, and left exactly as it is. {NOT_YET_UPGRADED}"],
        verification={
            "path": str(diagram_path), "file_type": "diagram", "valid": False,
            "issues": [{"severity": "error", "code": "E373", "message": NOT_YET_UPGRADED,
                        "location": str(diagram_path)}],
        },
        removed_entity_ids=[], removed_connection_ids=[], deleted_diagram=False,
    )
