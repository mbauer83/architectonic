"""The preflight: what a lift would create, skip, refuse, and leave outside the selection.

Lift is the moment a scratchpad stops being a sketch, so the one thing it must never do is
surprise anyone. Everything below is decided **before** a byte is written, from the aggregate and
the ontology alone — no repository, no staging tree, no write path. That is what makes the many
cases here affordable to cover, and it is why `plan_lift` returns a plan rather than performing
one: the same function answers the dialog and drives the execution, so what a person was shown is
what happens.

Four outcomes, and the distinction between them is the whole design:

* **create** — a note that is typed and holds no model reference becomes an entity; a typed link
  between two of them becomes a connection.
* **skip** — a note that already carries a `model_ref` is *reported and left alone*. A lift never
  writes back to the model: re-lifting a realized note would be bidirectional sync between a sketch
  and a governed model, and would silently clobber whatever was edited there since. A second lift
  therefore creates only what is new — which is the genuinely useful repeat case, because the
  *links* between already-lifted notes are usually what was added.
* **refuse** — something the ontology or the aggregate will not accept. Refusals **block the whole
  lift**, because the write is one transaction: half a lift is a state nobody asked for and nobody
  can name.
* **outside the selection** — a link with one end in and one end out. Not an error and not a
  refusal: it is a decision, and the person makes it by extending the selection or accepting that
  the link is not realized.

Narrowings (W128/W129) are warnings and pass. The relation exists; a specialization says it does not
apply here, which is worth knowing and is not the ontology refusing anything.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from src.domain.modules.module_registry import ModuleRegistry
from src.domain.scratchpad import Endpoint, Link, LinkVerdict, Note, Scratchpad

#: What would happen to one selected thing.
LiftOutcome = Literal["create", "skip", "refuse"]

#: The root model, as a group. `create_entity` reads an empty group as `uncategorized`, which is
#: where content belonging to no project already lives.
ROOT_MODEL = ""


@dataclass(frozen=True, slots=True)
class LiftTarget:
    """Where the content lands, resolved against the repository before planning.

    One target per lift, not per note. A lift is a coherent set by definition, and letting one
    selection scatter across several projects would make the preflight unreadable and the result
    hard to undo. Two destinations means two lifts, which is honest and rarely needed.
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

    kind: Literal["element", "connection"]
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
class LiftPlan:
    """The whole answer, in one payload."""

    target: LiftTarget
    items: tuple[LiftItem, ...] = ()
    outside_selection: tuple[OutsideSelection, ...] = ()
    #: A refusal of the lift itself rather than of any one item — an empty selection, an unknown
    #: note, a target whose meta-ontology is not this scratchpad's. Nothing is planned when set.
    refusal: str = ""

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


def plan_lift(
    scratchpad: Scratchpad,
    *,
    selection: Sequence[str],
    target: LiftTarget,
    verdict_of: Callable[[Link], LinkVerdict],
) -> LiftPlan:
    """What lifting *selection* into *target* would do. Pure: nothing is written and nothing read.

    `verdict_of` is the same verdict the canvas already renders beside each link, passed in rather
    than recomputed, so the preflight cannot disagree with what the person is looking at.
    """
    refusal = _plan_refusal(scratchpad, selection, target)
    if refusal:
        return LiftPlan(target=target, refusal=refusal)

    chosen = sorted(
        (note for note in scratchpad.notes if note.id in set(selection)),
        key=lambda note: note.id,
    )
    items = [_note_item(note) for note in chosen]
    inside = {note.id for note in chosen}
    refs = {note.id: _endpoint_ref(note) for note in chosen}

    for link in sorted(scratchpad.links, key=lambda candidate: candidate.id):
        if link.source in inside and link.target in inside:
            items.append(_link_item(scratchpad, link, verdict_of, refs))

    return LiftPlan(
        target=target,
        items=tuple(items),
        outside_selection=tuple(_outside(scratchpad, inside)),
    )


def _plan_refusal(scratchpad: Scratchpad, selection: Sequence[str], target: LiftTarget) -> str:
    if not selection:
        # An empty selection is a mis-click, not a request to lift nothing.
        return "Nothing is selected. Choose the notes to lift."
    known = {note.id for note in scratchpad.notes}
    unknown = sorted(set(selection) - known)
    if unknown:
        return f"The selection names notes this scratchpad does not have: {unknown}"
    if target.exists and target.meta_ontology and target.meta_ontology != scratchpad.meta_ontology:
        # A coercion here would put content into a project whose vocabulary never declared it.
        return (
            f"This scratchpad is {scratchpad.meta_ontology!r} and the project "
            f"{target.group!r} declares {target.meta_ontology!r}. Lift into a project with the "
            "same meta-ontology, or create a new one."
        )
    return ""


def _note_item(note: Note) -> LiftItem:
    """What would become of one selected note."""
    if note.model_ref is not None:
        kind = "bound to" if note.model_ref.kind == "bound" else "already realized as"
        return LiftItem(
            kind="element", id=note.id, outcome="skip", label=note.title,
            artifact_type=note.element_type or "", artifact_id=note.model_ref.artifact_id,
            reason=f"{kind} {note.model_ref.artifact_id} — the model is not the scratchpad's to rewrite",
        )
    if note.destination == "document" or note.document_type:
        return LiftItem(
            kind="element", id=note.id, outcome="refuse", label=note.title,
            reason="lifting a note to a document is not supported yet",
        )
    if note.destination != "element" or not note.element_type:
        return LiftItem(
            kind="element", id=note.id, outcome="refuse", label=note.title,
            reason="undecided — give it an element type, or take it out of the selection",
        )
    return LiftItem(
        kind="element", id=note.id, outcome="create", label=note.title,
        artifact_type=note.element_type, summary=note.body,
        specializations=(note.specialization,) if note.specialization else (),
    )


def _endpoint_ref(note: Note) -> str:
    """How a connection addresses this note: what it already is, or the alias its create will get."""
    return note.model_ref.artifact_id if note.model_ref is not None else f"$ref:{note.id}"


def _link_item(
    scratchpad: Scratchpad,
    link: Link,
    verdict_of: Callable[[Link], LinkVerdict],
    refs: dict[str, str],
) -> LiftItem:
    """What would become of one link whose ends are both selected."""
    label = _link_label(scratchpad, link)
    if link.model_ref is not None:
        return LiftItem(
            kind="connection", id=link.id, outcome="skip", label=label,
            artifact_type=link.connection_type or "", artifact_id=link.model_ref.artifact_id,
            reason=f"already realized as {link.model_ref.artifact_id}",
        )
    if not link.connection_type:
        return LiftItem(
            kind="connection", id=link.id, outcome="refuse", label=label,
            reason="untyped — a connection needs a relation, or take the link out of the selection",
        )
    verdict = verdict_of(link)
    if verdict.blocks:
        return LiftItem(
            kind="connection", id=link.id, outcome="refuse", label=label,
            artifact_type=link.connection_type, code=verdict.code, reason=verdict.message,
        )
    return LiftItem(
        kind="connection", id=link.id, outcome="create", label=label,
        artifact_type=link.connection_type,
        warning=verdict.message if verdict.kind == "narrowed" else "",
        source_ref=refs.get(link.source, ""),
        target_ref=refs.get(link.target, ""),
    )


def _link_label(scratchpad: Scratchpad, link: Link) -> str:
    source = scratchpad.note(link.source)
    target = scratchpad.note(link.target)
    relation = link.connection_type or "—"
    return f"{source.title if source else link.source} --{relation}--> {target.title if target else link.target}"


def _outside(scratchpad: Scratchpad, inside: set[str]) -> list[OutsideSelection]:
    """Links with exactly one end selected, named so the choice can be made rather than discovered."""
    found: list[OutsideSelection] = []
    for link in sorted(scratchpad.links, key=lambda candidate: candidate.id):
        ends = (link.source, link.target)
        if sum(end in inside for end in ends) != 1:
            continue
        stranded = next(end for end in ends if end not in inside)
        note = scratchpad.note(stranded)
        found.append(OutsideSelection(
            link_id=link.id, note_id=stranded, note_title=note.title if note else stranded,
        ))
    return found


@dataclass(frozen=True, slots=True)
class LiftReceipt:
    """What an execution actually did, correlated back to the notes and links that asked for it."""

    committed: bool = False
    #: note id / link id → the artifact the write allocated for it.
    realized: dict[str, str] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    operation_id: str = ""


def verdict_source(registry: ModuleRegistry, scratchpad: Scratchpad) -> Callable[[Link], LinkVerdict]:
    """The verdict function `plan_lift` needs, built from the registry once for the whole plan."""
    from src.application.scratchpad.verification import verdict_for  # noqa: PLC0415

    endpoints = {
        note.id: Endpoint(
            destination=note.destination,
            element_type=note.element_type,
            specialization=note.specialization,
            document_type=note.document_type,
        )
        for note in scratchpad.notes
    }

    def verdict_of(link: Link) -> LinkVerdict:
        return verdict_for(
            registry,
            meta_ontology=scratchpad.meta_ontology,
            source=endpoints.get(link.source, Endpoint()),
            target=endpoints.get(link.target, Endpoint()),
            connection_type=link.connection_type,
        )

    return verdict_of
