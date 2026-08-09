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

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
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

    kind: Literal["element", "document", "connection", "reference"]
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
class LiftPlan:
    """The whole answer, in one payload."""

    #: The distinct projects this lift would write into, one per frame that has something in it.
    targets: tuple[LiftTarget, ...] = ()
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
    targets: Mapping[str, LiftTarget],
    verdict_of: Callable[[Link], LinkVerdict],
) -> LiftPlan:
    """What lifting *selection* would do. Pure: nothing is written and nothing read.

    *targets* maps a frame's id to the project its content lands in; a frame with no entry lands in
    the root model, which is also where a note sitting in no frame goes.

    `verdict_of` is the same verdict the canvas already renders beside each link, passed in rather
    than recomputed, so the preflight cannot disagree with what the person is looking at.
    """
    chosen = sorted(
        (note for note in scratchpad.notes if note.id in set(selection)),
        key=lambda note: note.id,
    )
    used = {
        note.id: targets.get(scratchpad.area_of(note.id), LiftTarget()) for note in chosen
    }
    refusal = _plan_refusal(scratchpad, selection, used.values())
    if refusal:
        return LiftPlan(targets=_distinct(used.values()), refusal=refusal)

    items = [_note_item(note, used[note.id]) for note in chosen]
    inside = {note.id for note in chosen}
    refs = {note.id: _endpoint_ref(note) for note in chosen}

    for link in sorted(scratchpad.links, key=lambda candidate: candidate.id):
        if link.source in inside and link.target in inside:
            items.append(_link_item(scratchpad, link, verdict_of, refs))

    return LiftPlan(
        targets=_distinct(used.values()),
        items=tuple(_with_references(items)),
        outside_selection=tuple(_outside(scratchpad, inside)),
    )


def _with_references(items: list[LiftItem]) -> list[LiftItem]:
    """Fold each reference into the document it is recorded on.

    A reference is not an artifact. It is a link in a document's body pointing at a model file, so
    it is written *as part of* the document rather than beside it — which also means it cannot
    outlive a failed document create, and needs no second transaction to be consistent.

    The reference rows stay in the plan because a person must still see them: "this becomes a
    reference rather than a connection" is exactly the thing a preflight exists to say.
    """
    by_document: dict[str, list[str]] = {}
    for item in items:
        if item.kind == "reference" and item.outcome == "create":
            by_document.setdefault(item.source_ref, []).append(item.target_ref)
    if not by_document:
        return items
    return [
        replace(item, entity_refs=tuple(by_document.get(f"$ref:{item.id}", ())))
        if item.kind == "document" and item.outcome == "create" else item
        for item in items
    ]


def _distinct(targets: Iterable[LiftTarget]) -> tuple[LiftTarget, ...]:
    """The projects a lift touches, once each, in slug order — what the dialog lists."""
    return tuple(sorted({target for target in targets}, key=lambda item: item.group))


def _plan_refusal(
    scratchpad: Scratchpad, selection: Sequence[str], targets: Iterable[LiftTarget]
) -> str:
    if not selection:
        # An empty selection is a mis-click, not a request to lift nothing.
        return "Nothing is selected. Choose the notes to lift."
    known = {note.id for note in scratchpad.notes}
    unknown = sorted(set(selection) - known)
    if unknown:
        return f"The selection names notes this scratchpad does not have: {unknown}"
    for target in targets:
        if target.exists and target.meta_ontology and target.meta_ontology != scratchpad.meta_ontology:
            # A coercion here would put content into a project whose vocabulary never declared it.
            return (
                f"This scratchpad is {scratchpad.meta_ontology!r} and the project "
                f"{target.group!r} declares {target.meta_ontology!r}. Lift into a project with the "
                "same meta-ontology, or create a new one."
            )
    return ""


def _note_item(note: Note, target: LiftTarget) -> LiftItem:
    """What would become of one selected note, and which project it lands in."""
    if note.model_ref is not None:
        kind = "bound to" if note.model_ref.kind == "bound" else "already realized as"
        return LiftItem(
            kind="element", id=note.id, outcome="skip", label=note.title, target=target.group,
            artifact_type=note.element_type or "", artifact_id=note.model_ref.artifact_id,
            reason=f"{kind} {note.model_ref.artifact_id} — the model is not the scratchpad's to rewrite",
        )
    if note.destination == "document":
        if not note.document_type:
            return LiftItem(
                kind="document", id=note.id, outcome="refuse", label=note.title, target=target.group,
                reason="destined for a document but with no document type chosen",
            )
        return LiftItem(
            kind="document", id=note.id, outcome="create", label=note.title, target=target.group,
            artifact_type=note.document_type, summary=note.body,
        )
    if note.destination != "element" or not note.element_type:
        return LiftItem(
            kind="element", id=note.id, outcome="refuse", label=note.title, target=target.group,
            reason="undecided — give it an element type, or take it out of the selection",
        )
    return LiftItem(
        kind="element", id=note.id, outcome="create", label=note.title, target=target.group,
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
    reference = _reference_item(scratchpad, link, label, refs)
    if reference is not None:
        return reference
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


def _reference_item(
    scratchpad: Scratchpad, link: Link, label: str, refs: dict[str, str]
) -> LiftItem | None:
    """A link touching a document, which is a reference rather than a connection.

    No relation runs to a document, so this becomes a one-way reference **from the document to the
    model**, recorded on the document (ADR@1783406789). The direction drawn does not matter and is
    deliberately not preserved: a reference the model held would make the model depend on a
    commentary about it.

    Two documents produce nothing. They relate to each other in prose, not in the model, and there
    is no artifact for a lift to create.
    """
    source = scratchpad.note(link.source)
    target = scratchpad.note(link.target)
    if source is None or target is None:
        return None
    documents = [note for note in (source, target) if note.destination == "document"]
    elements = [note for note in (source, target) if note.destination == "element"]
    if not documents:
        return None
    document = documents[0]
    element = elements[0] if elements else None
    if element is None:
        return LiftItem(
            kind="reference", id=link.id, outcome="skip", label=label,
            reason="both ends are documents; documents relate to each other in prose, not in the model",
        )
    if link.model_ref is not None:
        return LiftItem(
            kind="reference", id=link.id, outcome="skip", label=label,
            artifact_id=link.model_ref.artifact_id, reason="already recorded on the document",
        )
    return LiftItem(
        kind="reference", id=link.id, outcome="create", label=label,
        reason="recorded on the document as a one-way reference into the model",
        source_ref=refs.get(document.id, ""),
        target_ref=refs.get(element.id, ""),
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
