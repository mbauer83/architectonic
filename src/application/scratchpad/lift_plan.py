"""The plan a lift is decided as, and the receipt it comes back with.

Values only, and no I/O: the same split the domain aggregate makes between `parts` and the root.
`lift.py` holds the reasoning over these, and `plan_lift` returning one of these rather than
performing anything is what lets the same function answer the dialog and drive the execution — so
what a person read is what runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: What would happen to one selected thing.
LiftOutcome = Literal["create", "skip", "refuse"]

#: The root model, as a group. `create_entity` reads an empty group as `uncategorized`, which is
#: where content belonging to no project already lives.
ROOT_MODEL = ""


@dataclass(frozen=True, slots=True)
class LiftTarget:
    """One project the content may land in, resolved against the repository before planning.

    **One target per frame**, not one per lift and not one per note. The frames are work
    archetypes: vision and strategy work is cross-project by nature, project work belongs to one
    project, enabling work is shared. Forcing a single destination would make the ordinary act —
    lift what is on this canvas — four separate lifts with the selection rebuilt by hand each time.

    Per *note* would be the other extreme and is the one worth refusing: the preflight would become
    a form rather than a report, and the frame is already the grouping a person can see.

    It costs nothing structurally — `create_entity` takes a group per item, so a lift spanning four
    projects is still one batch and one transaction.
    """

    group: str = ROOT_MODEL
    #: The meta-ontology the group declares, empty when it declares none or does not exist yet.
    meta_ontology: str = ""
    #: Whether the group is already in the registry. A lift may create one — "this thinking has
    #: become a project" is the normal way a project starts, and sending someone away to create a
    #: group would interrupt exactly the moment this feature exists to serve.
    exists: bool = False


@dataclass(frozen=True, slots=True)
class LiftItem:
    """One selected note or link, and what the lift would do with it."""

    kind: Literal["element", "document", "connection", "reference", "diagram"]
    id: str
    outcome: LiftOutcome
    label: str
    #: The element type or connection type this would create.
    artifact_type: str = ""
    #: What a skipped note is already, so the report names it rather than saying "already done".
    artifact_id: str = ""
    #: The verifier code a refusal corresponds to, when there is one.
    code: str = ""
    reason: str = ""
    #: A narrowing that does not block. Reported so nobody is surprised by a W128 after the fact.
    warning: str = ""
    #: Which project this lands in — the target of the frame the note sits in. Empty is the root
    #: model. A connection carries none: it lives with its source entity, wherever that went.
    target: str = ""
    #: For a document: the model files it will point at, as ids or `$ref:` aliases. Folded in from
    #: the reference rows below, because a reference is *recorded on the document* — it is part of
    #: writing the document, not a second artifact written beside it.
    entity_refs: tuple[str, ...] = ()
    #: The note's body, which becomes the entity's summary.
    summary: str = ""
    specializations: tuple[str, ...] = ()
    #: For a connection: how each end is addressed. Either an artifact id that already exists, or
    #: `$ref:<note id>` naming an entity this same batch creates — the alias `artifact_bulk_write`
    #: resolves, which is what lets a lift create both ends and the relation between them in one
    #: transaction.
    source_ref: str = ""
    target_ref: str = ""


@dataclass(frozen=True, slots=True)
class OutsideSelection:
    """A link with one end in the selection and one end out of it."""

    link_id: str
    note_id: str
    note_title: str


@dataclass(frozen=True, slots=True)
class LiftGrouping:
    """One of the scratchpad's groups, as a labelled box on the diagram a lift may draw.

    Groups map to `authored_groupings` and **frames map to nothing**. An area is a region of the
    workspace rather than an element of the picture, and with four of them it is far too coarse to
    be a box on a diagram; a group is a cluster someone drew *because* it means something, which is
    exactly what an authored grouping's label is for.
    """

    label: str
    members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LiftPlan:
    """The whole answer, in one payload."""

    #: The distinct projects this lift would write into, one per frame that has something in it.
    targets: tuple[LiftTarget, ...] = ()
    items: tuple[LiftItem, ...] = ()
    outside_selection: tuple[OutsideSelection, ...] = ()
    #: A refusal of the lift itself rather than of any one item — an empty selection, an unknown
    #: note, a target whose meta-ontology is not this scratchpad's. Nothing is planned when set.
    refusal: str = ""
    #: The boxes a drawn diagram would carry, empty when none was asked for.
    groupings: tuple[LiftGrouping, ...] = ()

    def of(self, outcome: LiftOutcome) -> tuple[LiftItem, ...]:
        return tuple(item for item in self.items if item.outcome == outcome)

    @property
    def warnings(self) -> tuple[LiftItem, ...]:
        return tuple(item for item in self.items if item.warning)

    @property
    def blocks(self) -> bool:
        """Whether the lift may proceed. A refusal anywhere stops all of it — one transaction."""
        return bool(self.refusal) or bool(self.of("refuse"))

    @property
    def is_empty(self) -> bool:
        """Nothing left to do: everything selected is already in the model."""
        return not self.of("create")


@dataclass(frozen=True, slots=True)
class LiftReceipt:
    """What an execution actually did, correlated back to the notes and links that asked for it."""

    committed: bool = False
    #: note id / link id → the artifact the write allocated for it.
    realized: dict[str, str] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    operation_id: str = ""
