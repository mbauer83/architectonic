"""Which operations of the catalog a write request states, read from its wire model alone.

The catalog's names are the application's (`src.application.operation_catalog`); this maps the
transports' request models onto them: a diagram replacement, an arrangement, a candidate's recorded
edits. Nothing on the write path asks it yet — the server decides a write by its carrier's intent, and
the projection answers every fine operation with that decision. These readers are the hook a
per-operation policy will decide on, kept beside the wire models they read and held by their tests
until it does.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from src.application.operation_catalog import (
    COMPOSE,
    GENERATE,
    INTENT_OPERATIONS,
    PLACE,
    SECTION_OPERATIONS,
    candidate_edit_operation,
)
from src.infrastructure.candidate_wire import RecordedEdit
from src.infrastructure.diagram_composition import DiagramReplacement
from src.infrastructure.diagram_layout_wire import ArrangeIntent, LayoutPatch


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
    return frozenset(candidate_edit_operation(edit.op) for edit in edits)
