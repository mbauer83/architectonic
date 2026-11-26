"""The one catalog of named operations a policy may allow or deny, and the writes that carry each.

A REST operation and the MCP tool that does the same thing are two *carriers* of one operation, so a
policy means the same on both surfaces: `changes_apply_candidate` is applied by `POST …/apply` and by
`change_set_apply`. An operation that is a whole write is named by its REST operation id.

The editing surfaces are finer than their writes. One canvas Save carries a rename, a move and a
restack in a single `PUT`, and one candidate write records several edits. Each of those is an
operation of its own, named here. The canvas offers or refuses its menu entries, keys and gestures by
these names, and the server projects a decision for every name in this catalog (`denied_operations`),
which is the only permission answer the GUI reads.

**What is decided today is the carrier's intent.** The server authorizes a write by its REST operation
id or MCP tool, through the intent the mutation manifests give it (`rest_mutation_manifest`,
`mutation_registration`); the projection answers each fine operation with the decision for the intent
its carriers share, so every fine operation of one Save is answered alike. Reading which fine
operations a request states is the infrastructure's (`stated_operations`, over the wire models), and
nothing on the write path consults it yet: it is the hook a per-operation policy will decide on, and a
fitness function holds every carrier of one operation to the same intent until then.

This module is application vocabulary: names, summaries and carriers, and which layout section and
arrangement intent each finer operation is. It knows no transport and no wire model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogOperation:
    """What an operation does, in a reader's words, and every REST operation and MCP tool that carries it."""

    summary: str
    carriers: frozenset[str]


_REPLACE = frozenset({"diagrams_replace_diagram", "artifact_replace_diagram"})
_ARRANGE = frozenset({"diagrams_arrange_diagram_layout", "artifact_arrange_diagram"})
_PATCH = frozenset({"diagrams_patch_diagram_layout", "artifact_arrange_diagram"})
_LAYOUT = _REPLACE | _ARRANGE | _PATCH
_RECORD = frozenset({"changes_record_operation", "change_set_record"})

COMPOSE = "diagram.compose"
PLACE = "diagram.layout.place"
ROUTE = "diagram.layout.route"
RESTACK = "diagram.layout.restack"
GENERATE = "diagram.body.generate"

#: Which layout section an entry is in decides which operation changing it is.
SECTION_OPERATIONS: Mapping[str, str] = {"elements": PLACE, "boxes": PLACE, "relations": ROUTE, "z": RESTACK}

INTENT_OPERATIONS: Mapping[str, tuple[str, ...]] = {
    "align": (PLACE,),
    "distribute": (PLACE,),
    "return_to_automatic": (PLACE, ROUTE),
    "straighten": (ROUTE,),
    "nest": (COMPOSE,),
    "unnest": (COMPOSE,),
    "create_grouping": (COMPOSE,),
    "delete_grouping": (COMPOSE,),
}

_MODEL_COMMANDS: Mapping[str, str] = {
    "model.element.create": "Create an element in the model",
    "model.element.rename": "Rename an element in the model",
    "model.element.edit": "Change an element's details in the model",
    "model.element.delete": "Delete an element from the model, with its relations",
    "model.relation.create": "Create a relation in the model",
    "model.relation.edit": "Change a relation's type, cardinalities, description or label in the model",
}

def candidate_edit_operation(op: str) -> str:
    """The operation recording one kind of candidate edit is: `change_set.` and the edit's kind."""
    return f"change_set.{op}"


_CANDIDATE_EDITS: Mapping[str, str] = {
    "create_entity": "Record creating an entity in a candidate",
    "edit_entity": "Record changing an entity in a candidate",
    "remove_entity": "Record removing an entity in a candidate",
    "add_connection": "Record adding a relation in a candidate",
    "edit_connection": "Record changing a relation in a candidate",
    "remove_connection": "Record removing a relation in a candidate",
    "drop": "Take back what a candidate records about one thing",
}

#: The writes the canvas, the candidate pages and the stress workspace make, each with its MCP twin.
_WRITES: Mapping[str, tuple[str, frozenset[str]]] = {
    "diagrams_replace_diagram": ("Save a diagram whole, with its layout and model edits", _REPLACE),
    "diagrams_patch_diagram_layout": (
        "Save changes to a diagram's layout", _PATCH,
    ),
    "diagrams_create_diagram": (
        "Create a diagram, as saving a generated view does",
        frozenset({"diagrams_create_diagram", "artifact_create_diagram"}),
    ),
    "diagrams_arrange_diagram_layout": ("Arrange a diagram by align, distribute, straighten or grouping", _ARRANGE),
    "diagrams_sync_diagram_to_model": (
        "Bring a diagram's drawn elements and relations into the model",
        frozenset({"diagrams_sync_diagram_to_model"}),
    ),
    "diagrams_delete_diagram": (
        "Delete a diagram", frozenset({"diagrams_delete_diagram", "artifact_delete_diagram"}),
    ),
    "promotion_execute_promotion": (
        "Promote artifacts to the enterprise repository",
        frozenset({"promotion_execute_promotion", "artifact_promote_to_enterprise"}),
    ),
    "changes_create_candidate": (
        "Create a candidate architecture", frozenset({"changes_create_candidate", "change_set_create"}),
    ),
    "changes_edit_candidate": (
        "Change a candidate's name, rationale, state or scope",
        frozenset({"changes_edit_candidate", "change_set_edit"}),
    ),
    "changes_record_operation": ("Record edits among a candidate's operations", _RECORD),
    "changes_rebase_candidate": (
        "Rebase a candidate onto the model as it is now", frozenset({"changes_rebase_candidate", "change_set_rebase"}),
    ),
    "changes_apply_candidate": (
        "Apply a candidate to the model", frozenset({"changes_apply_candidate", "change_set_apply"}),
    ),
    "changes_apply_candidate_as_target_state": (
        "Apply a candidate to the model as a target state beside the baseline",
        frozenset({"changes_apply_candidate_as_target_state", "change_set_apply_as_target_state"}),
    ),
    "changes_move_candidate_into_baseline": (
        "Move a candidate's target state into the baseline",
        frozenset({"changes_move_candidate_into_baseline", "change_set_move_into_baseline"}),
    ),
    "changes_withdraw_candidate_target_state": (
        "Withdraw a candidate's target state, leaving the baseline as it was",
        frozenset({"changes_withdraw_candidate_target_state", "change_set_withdraw_target_state"}),
    ),
    "changes_save_candidate_diagram": (
        "Save a candidate's picture as a diagram",
        frozenset({"changes_save_candidate_diagram", "change_set_save_diagram"}),
    ),
    "changes_integrate_candidates": (
        "Integrate candidates into a new one", frozenset({"changes_integrate_candidates", "change_set_integrate"}),
    ),
    "changes_delete_candidate": (
        "Delete a candidate nothing refers to", frozenset({"changes_delete_candidate", "change_set_delete"}),
    ),
    "documents_start_stress_analysis": (
        "Start a stress analysis", frozenset({"documents_start_stress_analysis", "analysis_start"}),
    ),
    "documents_hold_out_test_set": (
        "Hold out a stress analysis's test set",
        frozenset({"documents_hold_out_test_set", "analysis_hold_out_test_set"}),
    ),
    "documents_update_document_table": (
        "Change rows of a document's table, as the stress workspace's tables are",
        frozenset({"documents_update_document_table", "artifact_edit_document_table"}),
    ),
}

#: The writes the detail pages, the viewpoint pages and the document form make. An enterprise artifact is
#: written by its admin twin, which only a backend in admin mode allows; the projection answers why not.
_ARTIFACT_WRITES: Mapping[str, tuple[str, frozenset[str]]] = {
    "entities_update_entity": (
        "Change an entity, or record a change to an enterprise one",
        frozenset({"entities_update_entity", "artifact_edit_entity"}),
    ),
    "entities_delete_entity": (
        "Delete an entity and its relations", frozenset({"entities_delete_entity", "artifact_delete_entity"}),
    ),
    "connections_create_connection": (
        "Create a relation", frozenset({"connections_create_connection", "artifact_add_connection"}),
    ),
    "connections_update_connection": (
        "Change a relation", frozenset({"connections_update_connection", "artifact_edit_connection"}),
    ),
    "connections_delete_connection": ("Delete a relation", frozenset({"connections_delete_connection"})),
    "connections_update_connection_associations": (
        "Change what a relation is associated with",
        frozenset({"connections_update_connection_associations", "artifact_edit_connection_associations"}),
    ),
    "diagrams_delete_diagram": (
        "Delete a diagram", frozenset({"diagrams_delete_diagram", "artifact_delete_diagram"}),
    ),
    "admin_update_entity": ("Change an enterprise entity in place", frozenset({"admin_update_entity"})),
    "admin_delete_entity": ("Delete an enterprise entity", frozenset({"admin_delete_entity"})),
    "admin_create_connection": ("Create an enterprise relation", frozenset({"admin_create_connection"})),
    "admin_delete_connection": ("Delete an enterprise relation", frozenset({"admin_delete_connection"})),
    "admin_delete_diagram": ("Delete an enterprise diagram", frozenset({"admin_delete_diagram"})),
    "documents_create_document": (
        "Create a document", frozenset({"documents_create_document", "artifact_create_document"}),
    ),
    "viewpoints_create_viewpoint": (
        "Create a viewpoint", frozenset({"viewpoints_create_viewpoint", "artifact_viewpoint"}),
    ),
    "viewpoints_replace_viewpoint": (
        "Change a viewpoint's definition", frozenset({"viewpoints_replace_viewpoint", "artifact_viewpoint"}),
    ),
    "viewpoints_delete_viewpoint": (
        "Delete a viewpoint", frozenset({"viewpoints_delete_viewpoint", "artifact_viewpoint"}),
    ),
}

OPERATION_CATALOG: Mapping[str, CatalogOperation] = {
    **{name: CatalogOperation(summary, carriers) for name, (summary, carriers) in _WRITES.items()},
    **{name: CatalogOperation(summary, carriers) for name, (summary, carriers) in _ARTIFACT_WRITES.items()},
    COMPOSE: CatalogOperation(
        "Change what a diagram draws: add or remove elements, relations and occurrences, its boxes and their members",
        _REPLACE | _ARRANGE,
    ),
    PLACE: CatalogOperation("Move or size an element or a box on a diagram", _LAYOUT),
    ROUTE: CatalogOperation("Change a relation's route, its ends or its label's place", _LAYOUT),
    RESTACK: CatalogOperation(
        "Bring an element forward or send it back", _REPLACE | _PATCH,
    ),
    GENERATE: CatalogOperation("Give up a hand-written diagram body for a generated one", _REPLACE),
    **{name: CatalogOperation(summary, _REPLACE) for name, summary in _MODEL_COMMANDS.items()},
    **{candidate_edit_operation(op): CatalogOperation(summary, _RECORD) for op, summary in _CANDIDATE_EDITS.items()},
}
