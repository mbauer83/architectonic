"""Arrange and save a diagram from MCP, and read what arranging it needs — as the REST layout routes do.

Three tools over the same code the REST routes call: the layout read (the geometry route, without the
drawings only an editor paints with), the arrange (`PATCH …/layout` and `POST …/layout/arrange`), and the
canvas save (`PUT /api/diagrams/{id}`, model commands included). Each write goes through the write queue
as one named operation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]
from pydantic import Field

from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.diagram_composition import DiagramReplacement, replace_diagram
from src.infrastructure.diagram_layout_wire import ArrangeIntent, LayoutPatch, stated_intents
from src.infrastructure.mcp.artifact_mcp.context import (
    authoritative_callbacks_for,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool
from src.infrastructure.mcp.artifact_mcp.write._common import _out
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, READ_ONLY
from src.infrastructure.rendering.layout.diagram_geometry import stored_geometry
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.diagram_arrangement import arrange_diagram
from src.infrastructure.write.artifact_write.diagram_layout_patch import patch_diagram_layout
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

DiagramId = Annotated[str, Field(description="The diagram's id, in either spelling.")]
RepoRoot = Annotated[str | None, Field(description="The engagement repository; the active one when omitted.")]

ARRANGE_DIAGRAM_DESCRIPTION = """Change a diagram's layout or groupings: exactly one of `patch` or `intents`.

`patch`: entries by section (`elements`, `boxes`, `relations`, `z`) and layout key; each entry is null to
remove it, or {value, based_on?} — what it becomes and what you read it as (null for absent). A based_on
that no longer holds is refused and nothing is written; an entry without one is written whatever it holds.

`intents`, applied in order: align (keys ≥2, edge), distribute (keys ≥3, axis), straighten (relations),
return_to_automatic (keys; none: the whole layout); nest (keys, grouping), unnest (keys), create_grouping
(label, keys, parent?), delete_grouping (grouping). A grouping that selects its members by a rule gains or
loses none by listing. The answer includes the patch written, and `authored_groupings` where they changed.

Layout keys, and the stored entries a based_on states, are what artifact_query_diagram_layout answers.
dry_run defaults to true."""

QUERY_DIAGRAM_LAYOUT_DESCRIPTION = (
    "What arranging a diagram needs, as it is drawn now: each element's layout key, label, extent and the box "
    "it sits in; each box's key, kind (domain, type, grouping, element) and extent; each relation's key and "
    "the element keys it joins; and the stored layout block (absent while PlantUML arranges the diagram), "
    "whose entries are what a layout patch states as based_on. The canvas is in the same units."
)

REPLACE_DIAGRAM_DESCRIPTION = (
    "Save a diagram whole, with its layout and any model edits, in one write. "
    "replacement states its composition (diagram_type, name, entity_ids, "
    "connection_ids, diagram_entities — a further drawing of an element is an `occurrence` item "
    "{id, backing_entity_id} — and authored_groupings, with grouping_intents nest/unnest applied to them), "
    "its layout (a whole `layout` block, or a `layout_patch` reconciled with the new membership: entries "
    "naming what the diagram no longer holds are dropped and new members placed), and model `commands` "
    "(model.element.create / rename / edit / delete, model.relation.create / edit; an edit changes only the "
    "fields it states), all in one write or none. replacement.dry_run defaults to true. A layout_patch entry "
    "whose based_on no longer holds refuses the whole save. A body written by hand is not replaced unless "
    "manual_layout is false."
)


def _roots(repo_root: str | None) -> list[Path]:
    return resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)


def artifact_query_diagram_layout(artifact_id: DiagramId, repo_root: RepoRoot = None) -> dict[str, object]:
    roots = _roots(repo_root)
    record = repo_cached(roots_key(roots)).get_diagram(artifact_id)
    if record is None:
        raise ValueError(f"No diagram {artifact_id} is stored; artifact_query_list_artifacts lists them.")
    drawn = stored_geometry(
        parse_diagram_file(Path(record.path)), record.artifact_id, roots[0], process_runtime_catalogs().ontology,
    )
    return arrangement_of(drawn)


def arrangement_of(drawn: dict[str, Any]) -> dict[str, object]:
    """The geometry read without the drawings: keys, labels, extents and the stored layout."""
    elements, boxes, relations = drawn["elements"], drawn["boxes"], drawn["relations"]
    key_of = {element["alias"]: element["key"] for element in elements}
    key_of.update({box["alias"]: box["key"] for box in boxes if box.get("alias")})
    return {
        "artifact_id": drawn["artifact_id"],
        "name": drawn["name"],
        "canvas": drawn["canvas"],
        "elements": [
            {"key": one["key"], "label": one.get("label"), "extent": one["extent"],
             **({"inside": key_of.get(one["inside"], one["inside"])} if one.get("inside") else {})}
            for one in elements
        ],
        "boxes": [
            {"key": one["key"], "kind": one.get("kind"), "label": one.get("label"), "section": one.get("section"),
             "extent": one["extent"]}
            for one in boxes
        ],
        "relations": [
            {"key": one["key"], "source": key_of.get(one.get("source"), one.get("source")),
             "target": key_of.get(one.get("target"), one.get("target"))}
            for one in relations
        ],
        **({"layout": drawn["layout"]} if "layout" in drawn else {}),
    }


def artifact_arrange_diagram(
    *,
    artifact_id: DiagramId,
    patch: LayoutPatch | None = None,
    intents: Annotated[list[ArrangeIntent] | None, Field(description="Applied in order.")] = None,
    dry_run: bool = True,
    repo_root: RepoRoot = None,
) -> dict[str, object]:
    if (patch is None) == (intents is None):
        raise ValueError("State exactly one of patch or intents.")
    roots = _roots(repo_root)
    root, key = roots[0], roots_key(roots)
    verifier = verifier_for(key, include_registry=True)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    ontology = process_runtime_catalogs().ontology
    common: dict[str, Any] = {
        "repo_root": root, "verifier": verifier, "clear_repo_caches": clear_repo_caches,
        "assert_write_root": assert_engagement_write_root, "artifact_id": artifact_id, "dry_run": dry_run,
        "ontology": ontology,
    }
    try:
        if patch is not None:
            return patch_diagram_layout(patch=patch.stated(), **common).as_answer(with_patch=True)
        return arrange_diagram(
            stated=stated_intents(intents or []), store=repo_cached(key), **common,
        ).as_answer(with_patch=True)
    finally:
        mutation_context.finalize()


def artifact_replace_diagram(
    *, artifact_id: DiagramId, replacement: DiagramReplacement, repo_root: RepoRoot = None,
) -> dict[str, object]:
    roots = _roots(repo_root)
    key = roots_key(roots)
    mutation_context, record_changed = authoritative_callbacks_for(roots)

    def changed(paths: Path | list[Path]) -> None:  # one file, or every file a staged commit published
        for path in paths if isinstance(paths, list) else [paths]:
            record_changed(path)

    try:
        result = replace_diagram(
            artifact_id, replacement, root=roots[0], catalogs=process_runtime_catalogs(), live_repo=repo_cached(key),
            live_verifier=verifier_for(key, include_registry=True), clear_caches=changed,
        )
    finally:
        mutation_context.finalize()
    return _out(result, dry_run=replacement.dry_run)


def register_layout_read_tools(mcp: MCPServer) -> None:
    mcp.tool(
        name="artifact_query_diagram_layout", title="Artifact Query: Diagram Layout",
        description=QUERY_DIAGRAM_LAYOUT_DESCRIPTION, annotations=READ_ONLY, structured_output=True,
    )(artifact_query_diagram_layout)


def register_layout_tools(mcp: MCPServer) -> None:
    register_mutation_tool(
        mcp, artifact_arrange_diagram, name="artifact_arrange_diagram", title="Artifact Write: Arrange Diagram",
        description=ARRANGE_DIAGRAM_DESCRIPTION, annotations=DESTRUCTIVE_LOCAL_WRITE, structured_output=True,
    )
    register_mutation_tool(
        mcp, artifact_replace_diagram, name="artifact_replace_diagram", title="Artifact Write: Replace Diagram",
        description=REPLACE_DIAGRAM_DESCRIPTION, annotations=DESTRUCTIVE_LOCAL_WRITE, structured_output=True,
    )
