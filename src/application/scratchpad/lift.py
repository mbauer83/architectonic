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
from dataclasses import replace

from src.application.scratchpad.lift_plan import (
    ROOT_MODEL,
    LiftGrouping,
    LiftItem,
    LiftOutcome,
    LiftPlan,
    LiftReceipt,
    LiftTarget,
    OutsideSelection,
)
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.scratchpad import Endpoint, Link, LinkVerdict, Note, Scratchpad

#: Re-exported, so every caller keeps importing one name from one place regardless of which half of
#: this pair defines it — the same arrangement `startup_validation` uses for its two.
__all__ = [
    "ROOT_MODEL",
    "LiftGrouping",
    "LiftItem",
    "LiftOutcome",
    "LiftPlan",
    "LiftReceipt",
    "LiftTarget",
    "OutsideSelection",
    "plan_lift",
    "verdict_source",
]

def plan_lift(
    scratchpad: Scratchpad,
    *,
    selection: Sequence[str],
    targets: Mapping[str, LiftTarget],
    verdict_of: Callable[[Link], LinkVerdict],
    draw: bool = False,
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

    drawn = _diagram_item(scratchpad, items) if draw else None
    return LiftPlan(
        targets=_distinct(used.values()),
        items=tuple([*_with_references(items), *( [drawn] if drawn else [] )]),
        outside_selection=tuple(_outside(scratchpad, inside)),
        groupings=tuple(_groupings(scratchpad, inside)) if drawn else (),
    )


def _diagram_item(scratchpad: Scratchpad, items: list[LiftItem]) -> LiftItem | None:
    """A view of what this lift produced, offered rather than implied.

    Second-order and optional, and deliberately reported as its own row: it is drawn **after** the
    content commits, because it can only name entities that exist. A lift whose diagram fails is
    still a lift that happened, and the receipt says so rather than pretending the two were atomic.
    """
    drawn = [item for item in items if item.kind == "element" and item.outcome in ("create", "skip")]
    if not drawn:
        return None
    return LiftItem(
        kind="diagram", id=f"{scratchpad.artifact_id}#view", outcome="create",
        label=scratchpad.name, artifact_type="archimate-layered",
        reason="drawn after the content commits, since it can only name entities that exist",
        entity_refs=tuple(
            item.artifact_id or f"$ref:{item.id}" for item in drawn
        ),
    )


def _groupings(scratchpad: Scratchpad, inside: set[str]) -> list[LiftGrouping]:
    """The scratchpad's groups, as the diagram's boxes. Frames contribute nothing."""
    found: list[LiftGrouping] = []
    for group in sorted(scratchpad.groups, key=lambda item: item.id):
        members = tuple(
            (note.model_ref.artifact_id if note.model_ref else f"$ref:{note.id}")
            for member in sorted(group.members)
            if (note := scratchpad.note(member)) is not None and member in inside
        )
        if members:
            found.append(LiftGrouping(label=group.label, members=members))
    return found


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
