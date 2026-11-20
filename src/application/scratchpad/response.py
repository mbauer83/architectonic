"""The served shape: the stored document, plus what a reader needs and a file must not store.

Apart from `document`, which is the one mapping between the aggregate and the file. Everything added
here is *derived* — from geometry, or from a meta-ontology that may change under a stored
scratchpad — so persisting any of it would record an answer as though it were content. That is why
`to_document` takes no registry and this does, rather than one function taking an optional one and
meaning two things.
"""

from __future__ import annotations

from typing import Any

from src.application.scratchpad.document import drop_empty, to_document
from src.application.scratchpad.verification import (
    note_verdict_source,
    ontology_domains,
    types_in_domains,
    typing_options,
    verdict_source,
)
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.scratchpad import LinkVerdict, Scratchpad


def to_response(scratchpad: Scratchpad, *, group: str, registry: ModuleRegistry) -> dict[str, Any]:
    """The document as a read serves it.

    `group` is where the file sits, which the file cannot know about itself. `area` is derived from
    geometry, and a `verdict` from the meta-ontology — all served because otherwise every client
    re-implements them, and derives them slightly differently.

    **A verdict travels with what it is about rather than behind its own endpoint.** Deciding it
    again in a client would put the refusal-versus-warning split in two places — the one thing
    `classification_levels` exists to prevent — and would be blind to anything that is not a
    property of a type pair: a specialization's narrowing of a link, an area's narrowing of a note.
    Serving it here adds no route, no per-row request, and no second implementation.
    """
    document = to_document(scratchpad)
    document["group"] = group
    document["classification-levels"] = _levels_document(registry, scratchpad.meta_ontology)
    _serve_areas(scratchpad, document, registry)
    _serve_notes(scratchpad, document, registry)
    link_verdict_of = verdict_source(registry, scratchpad)
    stored_links = {link.id: link for link in scratchpad.links}
    for row in document.get("links", []):
        row["verdict"] = _verdict_document(link_verdict_of(stored_links[str(row["id"])]))
    return document


def _serve_areas(scratchpad: Scratchpad, document: dict[str, Any], registry: ModuleRegistry) -> None:
    for area, row in zip(
        sorted(scratchpad.areas, key=lambda item: item.id), document.get("areas", []), strict=False
    ):
        # The file says what a frame *declares*; the wire says what that currently resolves to. The
        # nested `permits` block is the file's vocabulary and has no business on the wire, where a
        # client would then have two places to look for one answer.
        row.pop("permits", None)
        # Derived, like a note's area: a frame declares the *domains* it holds, and the types that
        # follow from them are whatever the ontology currently declares. A frame that names types
        # outright keeps them; one that narrows nothing serves nothing, which reads as "anything".
        derived = area.permitted_element_types or types_in_domains(
            registry, scratchpad.meta_ontology, area.permitted_domains
        )
        if area.permitted_domains:
            row["permitted-domains"] = list(area.permitted_domains)
        if derived:
            row["permitted-element-types"] = list(derived)
        if area.permitted_document_types:
            row["permitted-document-types"] = list(area.permitted_document_types)


def _serve_notes(scratchpad: Scratchpad, document: dict[str, Any], registry: ModuleRegistry) -> None:
    domains = ontology_domains(registry, scratchpad.meta_ontology)
    note_verdict_of = note_verdict_source(registry, scratchpad)
    stored = {note.id: note for note in scratchpad.notes}
    for row in document.get("notes", []):
        note = stored[str(row["id"])]
        row["area"] = scratchpad.area_of(note.id)
        # Derived when a type is chosen, because the type implies it: two places to read the domain
        # from is two answers waiting to disagree, and the type is the more specific decision.
        derived = domains.get(note.element_type or "")
        if derived:
            row["domain"] = derived
        # Only a verdict that says something: an undecided note is the feature working, and a row
        # per note reading "unverified" would be noise on every read.
        verdict = note_verdict_of(note)
        if verdict.is_settled:
            row["verdict"] = _verdict_document(verdict)


def _levels_document(registry: ModuleRegistry, meta_ontology: str) -> list[dict[str, Any]]:
    """The ladder a note is refined down, and what each level offers.

    Served with the scratchpad because it is the scratchpad's meta-ontology that declares it: which
    levels there are, in what order, which must be reached before a lift, and where attributes
    attach. A client renders one control per level from this and names none of them itself.
    """
    return [
        {
            "id": offered.level.id,
            "label": offered.level.label,
            "source": offered.level.source,
            "required": offered.level.required,
            "carries-attributes": offered.level.carries_attributes,
            "options": [
                {"value": option.value, "within": option.within} for option in offered.options
            ],
        }
        for offered in typing_options(registry, meta_ontology)
    ]


def _verdict_document(verdict: LinkVerdict) -> dict[str, Any]:
    return drop_empty({
        "kind": verdict.kind,
        "code": verdict.code,
        "message": verdict.message,
        "alternatives": list(verdict.alternatives),
        "reverse-permitted": verdict.reverse_permitted or None,
        "narrowed-by": verdict.narrowed_by,
        "blocks": verdict.blocks or None,
    })
