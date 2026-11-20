"""Builders and generators for change sets, shared by the tests of everything that reads one.

The generators are derived from `edit_field_catalogue`: every field a kind admits, addressed the way
the catalogue says that field is addressed. A field added to the catalogue is generated here the
moment it is added, so the round trips are stated over what the vocabulary permits rather than over
a list someone remembered to extend.
"""

from __future__ import annotations

from typing import Any

from hypothesis import strategies as st

from src.application.change_sets.base import Base, BaseRevision, BaseValue, prose_revision
from src.application.change_sets.candidate_architecture import (
    CANDIDATE_STATES,
    CandidateArchitecture,
)
from src.application.change_sets.change_set import ChangeSet
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
from src.application.modeling.edit_field_catalogue import (
    CONTENT,
    KEYED,
    PROSE,
    ArtifactKind,
    creatable,
)
from src.domain.provisional_reference import provisional

GROUP = "GRP@1700000000.aaaaaa"


def change_set(*operations: Operation, repository_revision: str = "rev-1", **written: Any) -> ChangeSet:
    """A set of these operations, so a test states only what it is about."""
    return ChangeSet(tuple(operations), repository_revision, **written)


def candidate(*operations: Operation, id: str = "CA-1", **header: Any) -> CandidateArchitecture:  # noqa: A002
    """A draft candidate proposing these operations, with a sensible header."""
    defaults: dict[str, Any] = {"name": f"candidate {id}", "rationale": "", "state": "draft"}
    changes = header.pop("changes", None) or change_set(*operations)
    return CandidateArchitecture(id=id, changes=changes, **{**defaults, **header})


def create(ref: str, *, name: str | None = None, **fields: Any) -> CreateEntity:
    stated = {"artifact_type": "application-component", "name": name or ref, "group": GROUP}
    return CreateEntity(ref=ref, fields={**stated, **fields})


def edit(target: str, field: str, value: Any, *, was: Any = None, key: str | None = None) -> EditEntity:
    """An entity edit whose base is `was`, in whichever form the field calls for."""
    return EditEntity(target, field, value, base_for("entity", field, was), key=key)


def edit_connection(
    address: ConnectionAddress, field: str, value: Any, *, was: Any = None, key: str | None = None
) -> EditConnection:
    return EditConnection(address, field, value, base_for("connection", field, was), key=key)


def base_for(kind: ArtifactKind, field: str, was: Any) -> Base:
    return BaseRevision(prose_revision(was)) if field in PROSE[kind] else BaseValue(was)


def joins(source: str, target: str, connection_type: str = "serving") -> ConnectionAddress:
    return ConnectionAddress(source, connection_type, target)


# --- generators -----------------------------------------------------------------------------

#: Values the model's own serialisation admits, nested. Not field-shaped: what has to survive is any
#: value, and a field-specific fixture would be a second catalogue.
_scalars = st.none() | st.booleans() | st.integers(-9, 9) | st.text(max_size=5)
values = st.recursive(
    _scalars,
    lambda inner: st.lists(inner, max_size=2) | st.dictionaries(st.text(max_size=3), inner, max_size=2),
    max_leaves=3,
)
_names = st.text(alphabet="abcdefgh", min_size=1, max_size=4)
_ids = _names.map(lambda name: f"ENT@1.{name}")
_revisions = st.text(alphabet="0123456789abcdef", min_size=16, max_size=16)
_notes = st.sampled_from(["", "because the queue backs up"])


def _bases(kind: ArtifactKind, field: str) -> st.SearchStrategy[Base]:
    if field in PROSE[kind]:
        return st.builds(BaseRevision, _revisions)
    return st.builds(BaseValue, values)


def _addressed(kind: ArtifactKind) -> st.SearchStrategy[tuple[str, str | None]]:
    """Every (field, key) an edit of *kind* may address."""
    return st.sampled_from(sorted(CONTENT[kind])).flatmap(
        lambda field: st.tuples(st.just(field), _names if field in KEYED[kind] else st.none())
    )


@st.composite
def _entity_edits(draw: st.DrawFn, targets: st.SearchStrategy[str]) -> EditEntity:
    field, key = draw(_addressed("entity"))
    return EditEntity(
        draw(targets), field, draw(values), draw(_bases("entity", field)), key=key, note=draw(_notes)
    )


@st.composite
def _connection_edits(draw: st.DrawFn, addresses: st.SearchStrategy[ConnectionAddress]) -> EditConnection:
    field, key = draw(_addressed("connection"))
    return EditConnection(
        draw(addresses), field, draw(values), draw(_bases("connection", field)), key=key,
        note=draw(_notes),
    )


def _stated(kind: ArtifactKind, required: dict[str, Any]) -> st.SearchStrategy[dict[str, Any]]:
    optional = sorted(creatable(kind) - set(required))
    return st.dictionaries(st.sampled_from(optional), values, max_size=2).map(
        lambda fields: {**fields, **required}
    )


@st.composite
def operation_lists(draw: st.DrawFn) -> list[Operation]:
    """Operations that can stand together in one set: disjoint subjects per role, one per claim.

    Entities are partitioned into those the set creates, edits and removes, and connections into
    those it adds, edits and removes, so that no generated set trips a coherence refusal — those
    have their own tests, and a generator that produced them would mostly be discarded.
    """
    aliases = draw(st.lists(_names, max_size=2, unique=True))
    creates: list[Operation] = [
        CreateEntity(
            ref=alias,
            fields=draw(_stated("entity", {"artifact_type": "node", "name": alias, "group": GROUP})),
            artifact_id=draw(st.none() | st.just(f"NEW@1.{alias}")),
            note=draw(_notes),
        )
        for alias in aliases
    ]
    edited = [f"ENT@1.edited-{n}" for n in range(draw(st.integers(0, 2)))]
    gone = [f"ENT@1.gone-{n}" for n in range(draw(st.integers(0, 2)))]
    endpoints = [*edited, *(provisional(alias) for alias in aliases), "ENT@1.kept"]
    edits = draw(st.lists(_entity_edits(st.sampled_from(edited)), max_size=3)) if edited else []
    removals: list[Operation] = [
        RemoveEntity(target, BaseRevision(draw(_revisions)), note=draw(_notes)) for target in gone
    ]

    def address(role: str, number: int, ends: list[str]) -> ConnectionAddress:
        return ConnectionAddress(draw(st.sampled_from(ends)), f"{role}-{number}", draw(st.sampled_from(ends)))

    adds: list[Operation] = [
        AddConnection(address("adds", n, endpoints), draw(_stated("connection", {})), note=draw(_notes))
        for n in range(draw(st.integers(0, 2)))
    ]
    existing = [address("edits", n, ["ENT@1.kept", *edited]) for n in range(draw(st.integers(0, 2)))]
    connection_edits = (
        draw(st.lists(_connection_edits(st.sampled_from(existing)), max_size=3)) if existing else []
    )
    cut: list[Operation] = [
        RemoveConnection(address("cuts", n, ["ENT@1.kept", *gone]), BaseRevision(draw(_revisions)))
        for n in range(draw(st.integers(0, 2)))
    ]
    every = [*creates, *edits, *removals, *adds, *connection_edits, *cut]
    return list({operation.claim: operation for operation in every}.values())


@st.composite
def change_sets(draw: st.DrawFn) -> ChangeSet:
    """A whole set: every operation, addressed every way the catalogue permits."""
    return ChangeSet(tuple(draw(operation_lists())), draw(_revisions))


@st.composite
def candidates(draw: st.DrawFn) -> CandidateArchitecture:
    """A whole candidate: any state, with or without what it answers and satisfies."""
    return CandidateArchitecture(
        id=draw(_names.map(lambda name: f"CA-{name}")),
        name=draw(st.text(min_size=1, max_size=12)),
        rationale=draw(st.text(max_size=12)),
        state=draw(st.sampled_from(CANDIDATE_STATES)),
        changes=draw(change_sets()),
        answers=tuple(draw(st.lists(_names, max_size=2, unique=True))),
        satisfies=tuple(draw(st.lists(_ids, max_size=2, unique=True))),
    )
