"""The one catalog of named operations a policy may allow or deny, and the writes that carry each.

A REST operation and the MCP tool that does the same thing are two *carriers* of one operation, so a
policy means the same on both surfaces: `changes_apply_candidate` is applied by `POST …/apply` and by
`change_set_apply`. An operation that is a whole write is named by its REST operation id.

The editing surfaces are finer than their writes. One canvas Save carries a rename, a move and a
restack in a single `PUT`, and one candidate write records several edits. Each of those is an
operation of its own, named here, and `stated_operations` reads which of them a request states — so a
decision can be taken on each one, by the server, from the request alone. The canvas offers or refuses
its menu entries, keys and gestures by these names; the server projects a decision for every name in
this catalog (`denied_operations`), and that projection is the only permission answer the GUI reads.

What an operation's intent is stays the mutation manifests' to say (`rest_mutation_manifest`,
`mutation_registration`): every operation names at least one REST carrier, whose intent it takes, and
a fitness function holds every carrier of one operation to the same intent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from src.infrastructure.candidate_wire import RecordedEdit
from src.infrastructure.diagram_composition import DiagramReplacement
from src.infrastructure.diagram_layout_wire import ArrangeIntent, LayoutPatch


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

OPERATION_CATALOG: Mapping[str, CatalogOperation] = {
    **{name: CatalogOperation(summary, carriers) for name, (summary, carriers) in _WRITES.items()},
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
    **{f"change_set.{op}": CatalogOperation(summary, _RECORD) for op, summary in _CANDIDATE_EDITS.items()},
}


def _sections(sections: Iterable[str]) -> set[str]:
    return {SECTION_OPERATIONS[section] for section in sections if section in SECTION_OPERATIONS}


def _patched_sections(patch: LayoutPatch) -> set[str]:
    return _sections(section for section in patch.model_fields_set if getattr(patch, section) is not None)


def replacement_operations(replacement: DiagramReplacement) -> frozenset[str]:
    """What a diagram replacement does: it always composes, and each further part is an operation of its own."""
    layout = replacement.layout
    stated: set[str] = {COMPOSE, *(command.op for command in replacement.commands)}
    if replacement.layout_patch is not None:
        stated |= _patched_sections(replacement.layout_patch)
    if layout is not None:
        stated |= _sections(layout) or {PLACE}
    if replacement.manual_layout is False:
        stated.add(GENERATE)
    return frozenset(stated)


def arrangement_operations(patch: LayoutPatch | None, intents: Sequence[ArrangeIntent] | None) -> frozenset[str]:
    """What an arrangement does: a patch by the sections it changes, intents by what each one means."""
    stated = _patched_sections(patch) if patch is not None else set()
    for intent in intents or ():
        stated.update(INTENT_OPERATIONS[intent.intent])
    return frozenset(stated)


def recorded_operations(edits: Sequence[RecordedEdit]) -> frozenset[str]:
    """What recording *edits* in a candidate does: one operation for each kind of edit."""
    return frozenset(f"change_set.{edit.op}" for edit in edits)
