"""Changing which artifacts a diagram draws, as one operation with one meaning.

``entity_ids`` meant two different things on the two tools. On ``artifact_create_diagram`` it is the
membership: the PUML body is generated from it. On ``artifact_edit_diagram`` it only rewrote
``entity-ids-used`` and left the body alone — so removing an entity produced a diagram that *looked*
updated, still drew the entity, and still blocked its deletion; and the next ``puml="auto-sync"`` put
the reference back, because a reconcile unions the body's entities with the frontmatter's. The REST
replace route had it right all along: it resolves the selection and regenerates.

So membership is now one named operation, and it is honoured only where ``entity-ids-used`` *is* the
membership. Three kinds of diagram own their picture differently, and for those the request is refused
with the way to do it rather than half-performed:

* **model-backed** — a projector draws it from a scope binding; membership follows the model;
* **standalone** — ``diagram-entities`` is the membership, and the body is rendered from it;
* **manual-layout** — the author has ruled their body better than any regeneration, and sync keeps it
  verbatim, so a frontmatter-only change would be undone by the next reconcile.

Passing ``puml`` alongside ``entity_ids`` is a different request and stays as it was: the caller is
supplying both the picture and the membership, and reference inference reconciles them.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.infrastructure.rendering.diagram_selection import connections_among, resolve_diagram_selection

from .coerce import as_optional_str_list
from .parse_existing import ParsedDiagram


def is_scope_bound(parsed: ParsedDiagram) -> bool:
    """True when the diagram is owned by a projector (has a scoped-by binding or _scope_entity_id)."""
    for binding in parsed.bindings:
        if (
            binding.correspondence_kind == "scoped-by"
            and binding.subject.kind == "diagram"
            and binding.target.entity_id
        ):
            return True
    diagram_entities = parsed.frontmatter.get("diagram-entities")
    return isinstance(diagram_entities, dict) and bool(diagram_entities.get("_scope_entity_id"))


def is_standalone(parsed: ParsedDiagram) -> bool:
    """True when the diagram has explicit diagram-entities but is not scope-bound.

    Standalone diagrams store their full entity/connection set in frontmatter
    (without a projector binding).  They must be re-rendered, not reconciled via
    entity-ids-used, so deletion on empty inference is never correct for them.
    """
    de = parsed.frontmatter.get("diagram-entities")
    return isinstance(de, dict) and not is_scope_bound(parsed)


def membership_refusal(parsed: ParsedDiagram) -> str | None:
    """Why this diagram's membership cannot be set through ``entity_ids``, or None if it can.

    Each message names the operation that *does* change what the diagram draws, because a refusal
    whose only content is "no" leaves the caller to guess — and guessing is what produced the
    delete-and-recreate workaround this operation exists to remove.
    """
    if is_scope_bound(parsed):
        return (
            "This diagram is model-backed: a projector draws it from its scoped-by binding, so its "
            "membership follows the model rather than a list. Change the binding's target, or the "
            "model beneath it, and refresh with puml='auto-sync'."
        )
    if is_standalone(parsed):
        return (
            "This diagram's membership is its diagram-entities, which the body is rendered from — "
            "entity-ids-used only records what those entities reference. Pass diagram_entities to "
            "change what it draws."
        )
    if parsed.frontmatter.get("manual-layout") is True:
        return (
            "This diagram is manual-layout: its body is kept verbatim, so a membership change alone "
            "would leave the removed entity drawn and the next sync would record it again. Pass puml "
            "with the new body alongside entity_ids, or set manual_layout=false to let the body be "
            "generated."
        )
    return None


class RenderedMembership(NamedTuple):
    """What an edit must write so the diagram draws exactly the members it was given.

    Named *and* unpackable: the caller folds all three into the edit it is already making, and reading
    `puml, entity_ids, connection_ids = …` at that call site says what arrives.
    """

    puml: str
    entity_ids_used: list[str]
    connection_ids_used: list[str]
    authored_groupings: list[dict[str, object]]


def rendered_membership(
    *,
    repo_root: Path,
    store: object,
    verifier: ArtifactVerifier,
    artifact_id: str,
    entity_ids: list[str] | None,
    connection_ids: list[str] | None,
    authored_groupings: list[dict[str, object]] | None = None,
) -> RenderedMembership:
    """Resolve a stated membership into a body and the references that match it.

    Returns the fields rather than performing the write, so a membership change composes with
    everything else one edit call may carry — a rename, a status change, a group move — instead of
    being a separate write that silently drops them.

    ``connection_ids`` omitted means "whatever the model connects these members with", the rule
    ``artifact_create_diagram`` already applies — not "keep the old list", which would retain
    connections to entities that just left. Raises ``ValueError`` with the alternative when the
    diagram's body is not the generator's to rewrite.
    """
    from src.application.repo_path_helpers import diagram_source_root, resolve_diagram_source_path  # noqa: PLC0415
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body  # noqa: PLC0415

    from .parse_existing import parse_diagram_file  # noqa: PLC0415

    _find = verifier.registry.find_file_by_id if verifier.registry is not None else None
    diagram_path = resolve_diagram_source_path(repo_root, artifact_id, _find)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found under {diagram_source_root(repo_root)}")

    parsed = parse_diagram_file(diagram_path)
    refusal = membership_refusal(parsed)
    if refusal is not None:
        raise ValueError(refusal)

    fm = parsed.frontmatter
    members = entity_ids if entity_ids is not None else (as_optional_str_list(fm.get("entity-ids-used")) or [])
    wanted_connections = connection_ids if connection_ids is not None else connections_among(store, members)
    entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
        store, members, wanted_connections
    )

    raw_edge_labels = fm.get("edge-labels")
    raw_groupings = fm.get("authored-groupings")
    stored = [g for g in raw_groupings if isinstance(g, dict)] if isinstance(raw_groupings, list) else []
    # Supplied groupings replace the stored ones wholesale, as membership does: a caller listing the
    # boxes it wants is stating them all, and merging would make a group impossible to delete.
    groupings = stored if authored_groupings is None else authored_groupings
    return RenderedMembership(
        puml=generate_archimate_puml_body(
            str(fm.get("name", "")),
            entities,
            connections,
            diagram_type=str(fm.get("diagram-type", "archimate")),
            edge_labels=dict(raw_edge_labels) if isinstance(raw_edge_labels, dict) else None,
            authored_groupings=groupings or None,
        ),
        entity_ids_used=entity_ids_used,
        connection_ids_used=connection_ids_used,
        authored_groupings=groupings,
    )
