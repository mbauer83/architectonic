"""Applying a candidate as a target state: the operations that put it in the model beside the baseline.

A candidate applied directly changes the model it reads. Applied as a target state it leaves the
baseline as it is and writes its proposal next to it, as ArchiMate content a reader can see:

* an element it adds is created as itself, as a draft;
* an element it changes is represented by "‹name› (target)", of the same type, saying what the
  candidate says about it, with its relations and an association to the original that traces it;
* a Baseline and a Target plateau aggregate the originals and their replacements, the elements it
  removes in the baseline, and a «gap» assessment is associated with both.

**One representation, one way in.** The candidate keeps its operation list, unapplied to the originals.
What is written here is another operation list generated from it, written through the same write path
as any other, and recorded on the candidate (`TargetState`) so that moving into the baseline
(`target_move`) can take it away again.

**What counts as changed** is decided by the operations alone: an element an edit names, and both ends
of a relation the candidate adds, edits or removes between elements the model already holds. A relation
to an element the candidate adds is already the target state's through that element, and the elements
a candidate removes stay in the baseline without a copy.

**Pure.** Ids are allocated and the permitted relations read by the caller (`Allocate`, `Permits`), and
the relations a target state is written with are the ontology's (`TargetStateRelations`), handed in.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, TypeAlias

from src.application.change_sets.candidate_architecture import CandidateArchitecture, TargetState
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.composition import compose
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    Operation,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.reading import FieldValues, ModelReading, RecordedReading
from src.application.modeling.edit_field_catalogue import creatable
from src.domain.artifact_id import canonical_entity_key
from src.domain.ontology_representation.target_state_relations import TargetStateRelations
from src.domain.provisional_reference import alias_of, provisional

#: A new id for an element of this type and name.
Allocate: TypeAlias = Callable[[str, str], str]
#: Whether the ontology permits a relation of this type from a source type to a target type.
Permits: TypeAlias = Callable[[str, str, str], bool]

PLATEAU = "plateau"
#: The «gap»: the ontology's specialization of an assessment.
GAP_TYPE, GAP = "assessment", "gap"
#: Where everything a target state writes starts, and what a move sets what it added to.
DRAFT, ACTIVE = "draft", "active"


@dataclass(frozen=True, slots=True)
class TargetPlan:
    """What applying a candidate as a target state writes, and where that is recorded."""

    changes: ChangeSet
    state: TargetState
    #: The elements a plateau may not aggregate, by type, which stand in their state unheld.
    unheld: tuple[str, ...] = ()
    #: The id each element the operations create is given, by the alias they name it with.
    chosen: Mapping[str, str] = field(default_factory=dict)

    @property
    def shown(self) -> tuple[Operation, ...]:
        """The operations as a reader is shown them: every element named by the id it is given."""
        return tuple(named_by_id(operation, self.chosen) for operation in self.changes.operations)


def target_plan(
    candidate: CandidateArchitecture,
    live: RecordedReading,
    *,
    revision: str,
    allocate: Allocate,
    permits: Permits,
    relations: TargetStateRelations,
    beneath: Sequence[ChangeSet] = (),
) -> TargetPlan:
    """The operations that put *candidate* in the model as a target state, over the *live* model, related by
    the ontology's *relations*."""
    operations = candidate.changes.operations
    composed = compose(candidate.changes, live, beneath=beneath)
    created = candidate.changes.created
    removed = frozenset(op.target for op in operations if isinstance(op, RemoveEntity))
    changed = _changed(operations, frozenset(created), removed)

    def fields_of(reference: str) -> FieldValues:
        return composed.entity(reference) or live.entity(reference) or {}

    added = {
        create.ref: create.artifact_id or allocate(str(create.fields["artifact_type"]), str(create.fields["name"]))
        for create in created.values()
    }
    copies = {original: allocate(_type(fields_of(original)), _copied_name(fields_of(original))) for original in changed}
    alias = {original: f"target-of-{original}" for original in changed}
    home = _home_group([*changed, *created, *removed], fields_of)
    names = {
        "baseline": f"Baseline: {candidate.name}", "target": f"Target: {candidate.name}",
        "gap": f"Gap: {candidate.name}",
    }
    ids = {part: allocate(GAP_TYPE if part == "gap" else PLATEAU, name) for part, name in names.items()}
    refs = {part: f"target-state-{part}" for part in names}

    def routed(end: str) -> str:
        return provisional(alias[end]) if end in alias else end

    writes: list[Operation] = [
        *(CreateEntity(c.ref, {**c.fields, "status": DRAFT}, artifact_id=added[c.ref]) for c in created.values()),
        *(_copy(o, fields_of(o), alias[o], copies[o]) for o in changed),
        *(_trace(relations, provisional(alias[o]), o, fields_of(o), candidate.name) for o in changed),
        *_relations(_addresses(live, operations), composed, routed, frozenset(created) | set(alias), removed),
        CreateEntity(refs["baseline"], _plateau(names["baseline"], home), artifact_id=ids["baseline"]),
        CreateEntity(refs["target"], _plateau(names["target"], home), artifact_id=ids["target"]),
        CreateEntity(refs["gap"], _gap(names["gap"], home, candidate.rationale), artifact_id=ids["gap"]),
        *(
            AddConnection(ConnectionAddress(provisional(refs["gap"]), relations.trace, provisional(refs[plateau])), {})
            for plateau in ("baseline", "target")
        ),
    ]
    target_members = [(r, _type(fields_of(r))) for r in created] + [
        (provisional(alias[o]), _type(fields_of(o))) for o in changed
    ]
    baseline_members = [(o, _type(fields_of(o))) for o in (*changed, *sorted(removed))]
    held, unheld = _held(provisional(refs["target"]), target_members, permits, relations.holds)
    held_too, unheld_too = _held(provisional(refs["baseline"]), baseline_members, permits, relations.holds)
    state = TargetState(ids["baseline"], ids["target"], ids["gap"], copies=copies, added=added)
    chosen = {**added, **{alias[o]: copies[o] for o in changed}, **{refs[part]: ids[part] for part in refs}}
    return TargetPlan(
        ChangeSet((*writes, *held, *held_too), revision), state, tuple(sorted({*unheld, *unheld_too})), chosen,
    )


def named_by_id(operation: Operation, chosen: Mapping[str, str]) -> Operation:
    """*operation* with each element it names by an alias in *chosen* named by the id it is given instead."""

    def by_id(reference: str) -> str:
        alias = alias_of(reference)
        return chosen.get(alias, reference) if alias is not None else reference

    match operation:
        case CreateEntity():
            return operation
        case EditEntity(target=target) | RemoveEntity(target=target):
            return replace(operation, target=by_id(target))
        case AddConnection(address=address) | EditConnection(address=address) | RemoveConnection(address=address):
            return replace(operation, address=ConnectionAddress(
                by_id(address.source_entity), address.connection_type, by_id(address.target_entity),
            ))


def _changed(operations: Sequence[Operation], created: frozenset[str], removed: frozenset[str]) -> tuple[str, ...]:
    """The elements the model holds whose own record or relations the operations change."""
    edited = {op.target for op in operations if isinstance(op, EditEntity)}
    relinked = {
        end
        for op in operations if isinstance(op, AddConnection | EditConnection | RemoveConnection)
        if not set(op.address.endpoints) & (created | removed)
        for end in op.address.endpoints
    }
    return tuple(sorted((edited | relinked) - removed - created))


def _addresses(live: RecordedReading, operations: Iterable[Operation]) -> list[ConnectionAddress]:
    added = [op.address for op in operations if isinstance(op, AddConnection)]
    return sorted({*live.connections, *added}, key=str)


def _relations(
    addresses: Iterable[ConnectionAddress],
    composed: ModelReading,
    routed: Callable[[str], str],
    targeted: frozenset[str],
    removed: frozenset[str],
) -> list[AddConnection]:
    """Every relation the target state holds that the baseline does not: each one touching an element the
    candidate adds or a copy, with its ends moved to the copies."""
    relations: dict[ConnectionAddress, AddConnection] = {}
    for address in addresses:
        fields = composed.connection(address)
        if fields is None or set(address.endpoints) & removed or not set(address.endpoints) & targeted:
            continue
        moved = ConnectionAddress(routed(address.source_entity), address.connection_type, routed(address.target_entity))
        relations.setdefault(moved, AddConnection(moved, stated(fields, "connection")))
    return list(relations.values())


def stated(fields: Mapping[str, Any], kind: str = "entity") -> dict[str, Any]:
    """What a create may state of *fields*, leaving out what says nothing."""
    allowed = creatable("entity" if kind == "entity" else "connection")
    return {
        name: list(value) if isinstance(value, tuple) else value
        for name, value in fields.items() if name in allowed and value not in (None, "", (), [], {})
    }


def _copy(original: str, fields: FieldValues, ref: str, artifact_id: str) -> CreateEntity:
    return CreateEntity(
        ref, {**stated(fields), "name": _copied_name(fields), "status": DRAFT}, artifact_id=artifact_id,
        note=f"The target state of {original}.",
    )


def _trace(
    relations: TargetStateRelations, copy: str, original: str, fields: FieldValues, candidate: str,
) -> AddConnection:
    return AddConnection(
        ConnectionAddress(copy, relations.trace, original),
        {"description": f"The target state of {_name(fields)} in {candidate}."},
    )


def _plateau(name: str, group: str) -> dict[str, Any]:
    return {"artifact_type": PLATEAU, "name": name, "group": group, "status": DRAFT}


def _gap(name: str, group: str, rationale: str) -> dict[str, Any]:
    gap = {"artifact_type": GAP_TYPE, "name": name, "group": group, "status": DRAFT, "specializations": [GAP]}
    return gap | ({"summary": rationale} if rationale else {})


def _held(
    plateau: str, members: Iterable[tuple[str, str]], permits: Permits, holds: str,
) -> tuple[list[AddConnection], list[str]]:
    """Relations *holds* from *plateau* to each member it may hold, and the types of those it may not."""
    listed = list(members)
    held = [
        AddConnection(ConnectionAddress(plateau, holds, ref), {})
        for ref, kind in listed if permits(PLATEAU, kind, holds)
    ]
    return held, [kind for _ref, kind in listed if not permits(PLATEAU, kind, holds)]


def _home_group(subjects: Iterable[str], fields_of: Callable[[str], FieldValues]) -> str:
    """The group the plateaus and the gap are filed in: the first subject's, in a stable order."""
    groups = [str(fields_of(subject).get("group") or "") for subject in sorted(subjects, key=canonical_entity_key)]
    return next((group for group in groups if group), "")


def _type(fields: FieldValues) -> str:
    return str(fields.get("artifact_type") or "")


def _name(fields: FieldValues) -> str:
    return str(fields.get("name") or "")


def _copied_name(fields: FieldValues) -> str:
    """The name of a changed element's "(target)" copy: what the candidate names it, marked as the target's."""
    return f"{_name(fields)} (target)"
