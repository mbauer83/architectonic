"""The one mapping between a `Scratchpad` and a plain document.

There is exactly one, because the two consumers want the same thing. The file on disk and the REST
payload were designed to speak the same kebab-case vocabulary on purpose — so a person reading a
response and a person reading the file are reading one document — and writing that mapping twice
would have made the deliberate sameness a coincidence maintained by hand, with two places to drift
and no test able to see the drift until a round trip through the wrong one lost a field.

So: `to_document` and `from_document` here, `yaml.safe_dump` in the repository, and two derived
conveniences added by the REST layer that the file has no business storing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.application.scratchpad.ports import ScratchpadSummary

if TYPE_CHECKING:
    from src.domain.modules.module_registry import ModuleRegistry

from src.domain.scratchpad import (
    Area,
    Endpoint,
    Group,
    Layout,
    Link,
    ModelRef,
    ModelRefKind,
    Note,
    Point,
    Rect,
    Scratchpad,
    scratchpad_from_parts,
)


def _drop_empty(mapping: dict[str, Any]) -> dict[str, Any]:
    """Omit what carries no information. A document full of `null`s reads as a document full of
    decisions, and an untyped note should look untyped."""
    return {key: value for key, value in mapping.items() if value not in (None, "", (), [], {})}


def _ref_document(ref: ModelRef | None) -> dict[str, Any] | None:
    return {"artifact-id": ref.artifact_id, "kind": ref.kind} if ref else None


def _ref(raw: object) -> ModelRef | None:
    """An unrecognised `kind` reads as `bound`, the weaker claim: `realized` asserts that a lift
    created the content, which is not something to infer from a typo."""
    if not isinstance(raw, dict) or not raw.get("artifact-id"):
        return None
    kind: ModelRefKind = "realized" if str(raw.get("kind")) == "realized" else "bound"
    return ModelRef(artifact_id=str(raw["artifact-id"]), kind=kind)


def to_document(scratchpad: Scratchpad) -> dict[str, Any]:
    """The aggregate as a plain document, collections in stable id order, layout last.

    Stable order is what makes a no-op save produce no diff; layout last is what keeps an
    afternoon of tidying and an afternoon of thinking in different parts of the file.
    """
    document = _drop_empty({
        "artifact-id": scratchpad.artifact_id,
        "artifact-type": "scratchpad",
        "name": scratchpad.name,
        "description": scratchpad.description,
        "version": scratchpad.version,
        "status": scratchpad.status,
        "meta-ontology": scratchpad.meta_ontology,
        "attributes": dict(scratchpad.attributes),
        "areas": [
            _drop_empty({
                "id": area.id,
                "label": area.label,
                "permits": _drop_empty({
                    "elements": list(area.permitted_element_types),
                    "documents": list(area.permitted_document_types),
                }),
            })
            for area in sorted(scratchpad.areas, key=lambda item: item.id)
        ],
        "notes": [
            _drop_empty({
                "id": note.id,
                "title": note.title,
                "body": note.body,
                "destination": note.destination if note.destination != "undecided" else "",
                "element-type": note.element_type,
                "specialization": note.specialization,
                "document-type": note.document_type,
                "model-ref": _ref_document(note.model_ref),
                "attributes": dict(note.attributes),
            })
            for note in sorted(scratchpad.notes, key=lambda item: item.id)
        ],
        "groups": [
            _drop_empty({"id": group.id, "label": group.label, "members": sorted(group.members)})
            for group in sorted(scratchpad.groups, key=lambda item: item.id)
        ],
        "links": [
            _drop_empty({
                "id": link.id,
                "source": link.source,
                "target": link.target,
                "connection-type": link.connection_type,
                "model-ref": _ref_document(link.model_ref),
            })
            for link in sorted(scratchpad.links, key=lambda item: item.id)
        ],
    })
    layout = _drop_empty({
        "areas": {key: [rect.x, rect.y, rect.width, rect.height]
                  for key, rect in sorted(scratchpad.layout.areas.items())},
        "notes": {key: [point.x, point.y] for key, point in sorted(scratchpad.layout.notes.items())},
        "groups": {key: [rect.x, rect.y, rect.width, rect.height]
                   for key, rect in sorted(scratchpad.layout.groups.items())},
    })
    if layout:
        document["layout"] = layout
    return document


def from_document(raw: dict[str, Any], *, artifact_id: str | None = None) -> Scratchpad:
    """Rebuild and validate. `artifact_id` overrides the document's, so an address in a URL wins
    over one a client put in a body — the two disagreeing is a client bug, not a rename."""

    def rows(key: str) -> list[dict[str, Any]]:
        value = raw.get(key)
        return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []

    raw_layout = raw.get("layout")
    layout_raw: dict[str, Any] = raw_layout if isinstance(raw_layout, dict) else {}

    def rects(key: str) -> dict[str, Rect]:
        block = layout_raw.get(key)
        return {str(k): Rect(*(float(n) for n in v)) for k, v in block.items()} if isinstance(block, dict) else {}

    points_block = layout_raw.get("notes")
    points = (
        {str(k): Point(float(v[0]), float(v[1])) for k, v in points_block.items()}
        if isinstance(points_block, dict) else {}
    )

    return scratchpad_from_parts(
        artifact_id=artifact_id or str(raw.get("artifact-id") or ""),
        name=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        version=str(raw.get("version") or "0.1.0"),
        status=str(raw.get("status") or "draft"),
        meta_ontology=str(raw.get("meta-ontology") or "archimate-4"),
        attributes=dict(raw.get("attributes") or {}),
        areas=[
            Area(
                id=str(row.get("id") or ""),
                label=str(row.get("label") or ""),
                permitted_element_types=tuple(str(v) for v in (row.get("permits") or {}).get("elements") or ()),
                permitted_document_types=tuple(str(v) for v in (row.get("permits") or {}).get("documents") or ()),
            )
            for row in rows("areas")
        ],
        notes=[
            Note(
                id=str(row.get("id") or ""),
                title=str(row.get("title") or ""),
                body=str(row.get("body") or ""),
                destination=str(row.get("destination") or "undecided"),  # type: ignore[arg-type]
                element_type=row.get("element-type"),
                specialization=row.get("specialization"),
                document_type=row.get("document-type"),
                model_ref=_ref(row.get("model-ref")),
                attributes=dict(row.get("attributes") or {}),
            )
            for row in rows("notes")
        ],
        links=[
            Link(
                id=str(row.get("id") or ""),
                source=str(row.get("source") or ""),
                target=str(row.get("target") or ""),
                connection_type=row.get("connection-type"),
                model_ref=_ref(row.get("model-ref")),
            )
            for row in rows("links")
        ],
        groups=[
            Group(
                id=str(row.get("id") or ""),
                label=str(row.get("label") or ""),
                members=tuple(str(v) for v in row.get("members") or ()),
            )
            for row in rows("groups")
        ],
        layout=Layout(areas=rects("areas"), notes=points, groups=rects("groups")),
    )


def summary_to_document(summary: ScratchpadSummary) -> dict[str, Any]:
    """One list row. Both surfaces render the same keys, so they render them from here — the
    alternative is two copies of a field list, and the one nobody edits is the one that goes stale.
    """
    return {
        "artifact-id": summary.artifact_id,
        "name": summary.name,
        "description": summary.description,
        "status": summary.status,
        "version": summary.version,
        "group": summary.group,
        "meta-ontology": summary.meta_ontology,
        "note-count": summary.note_count,
    }


def to_response(
    scratchpad: Scratchpad, *, group: str, registry: "ModuleRegistry"
) -> dict[str, Any]:
    """The served shape: the document, plus what a reader needs and a file must not store.

    `group` is where the file sits, which the file cannot know about itself. `area` is derived from
    geometry, and a link's `verdict` from the meta-ontology — both served because otherwise every
    client re-implements them, and derives them slightly differently.

    **The verdict travels with the link rather than behind its own endpoint.** Phase C planned for
    the canvas to call `/api/ontology/pairs` and decide for itself; that predates the two-tier
    verdict being a domain concept, and re-deciding it in the client would put the E126-versus-W128
    split in two places — the one thing `classification_levels` exists to prevent. It would also be
    blind to specialization narrowing, which is not a property of a type *pair*. Serving it here
    adds no route, no per-link request, and no second implementation.

    Only the *served* shape carries verdicts. The file must not: a verdict is derived from an
    ontology that may change under a stored scratchpad, so persisting one would record an answer as
    though it were content. That is why `to_document` exists beside this and takes no registry,
    rather than this taking an optional one and meaning two things.
    """
    document = to_document(scratchpad)
    document["group"] = group
    for note in document.get("notes", []):
        note["area"] = scratchpad.area_of(str(note["id"]))
    endpoints = {note.id: _endpoint(note) for note in scratchpad.notes}
    for link in document.get("links", []):
        link["verdict"] = _verdict_document(scratchpad, link, endpoints, registry)
    return document


def _endpoint(note: Note) -> Endpoint:
    return Endpoint(
        destination=note.destination,
        element_type=note.element_type,
        specialization=note.specialization,
        document_type=note.document_type,
    )


def _verdict_document(
    scratchpad: Scratchpad,
    link: dict[str, Any],
    endpoints: dict[str, Endpoint],
    registry: "ModuleRegistry",
) -> dict[str, Any]:
    from src.application.scratchpad.verification import verdict_for  # noqa: PLC0415

    verdict = verdict_for(
        registry,
        meta_ontology=scratchpad.meta_ontology,
        source=endpoints.get(str(link["source"]), Endpoint()),
        target=endpoints.get(str(link["target"]), Endpoint()),
        connection_type=link.get("connection-type"),
    )
    return _drop_empty({
        "kind": verdict.kind,
        "code": verdict.code,
        "message": verdict.message,
        "alternatives": list(verdict.alternatives),
        "reverse-permitted": verdict.reverse_permitted or None,
        "narrowed-by": verdict.narrowed_by,
        "blocks": verdict.blocks or None,
    })
