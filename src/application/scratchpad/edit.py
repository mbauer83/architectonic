"""A change to a scratchpad, expressed as what changed.

`replace` writes the aggregate whole, which is right for the canvas — it holds the document in
memory and saves one coherent state — and cumbersome everywhere else. An agent removing one note
had to read the entire canvas and send it all back: two full documents to change three lines, a
payload that grows with the size of the thinking rather than with the size of the edit, and a wider
window for the version to move under it.

So this is the same write, addressed by delta. It is emphatically **not** a second way into
storage: the delta is turned into an aggregate, and that aggregate is validated and saved by the
one path `replace` uses. The invariants, the refusal vocabulary and the version token are identical,
because they are the same code.

Two rules make it predictable:

* **A patch is a merge patch**, in the vocabulary `scratchpad_read` returns. A key absent from a
  patch leaves the stored value alone; a key set to `null` clears it; anything else sets it. This is
  the one place the two writes differ, and they differ on purpose — under `replace`, omission *is*
  removal, because the document sent is the whole truth.
* **A removal takes with it what the aggregate says it takes.** Removing a note removes its links,
  its group memberships and its placement, because `Scratchpad.without_note` says so and this
  routes through it rather than restating it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.application.scratchpad.document import from_document, to_document
from src.application.scratchpad.requests import refuse_unknown_destinations
from src.domain.scratchpad import Scratchpad, ScratchpadError

#: The collections a scratchpad document holds, each a list of rows carrying an `id`. Named once so
#: a delta cannot address something the document has no such thing as.
COLLECTIONS: tuple[str, ...] = ("areas", "notes", "groups", "links")

#: Which of those also have a geometry entry keyed by the same id. A row and its rectangle are one
#: thing to a reader, so removing the row removes the rectangle.
_PLACED: tuple[str, ...] = ("areas", "notes", "groups")


@dataclass(frozen=True, slots=True)
class ScratchpadEdit:
    """What changed. Every field is optional; an edit that changes nothing is refused, not ignored."""

    #: collection name → the ids to remove from it.
    remove: Mapping[str, Sequence[str]] = field(default_factory=dict)
    #: collection name → merge patches, each identified by its `id`. An id the scratchpad does not
    #: have is a creation, which is how a note is added without sending the canvas.
    upsert: Mapping[str, Sequence[Mapping[str, Any]]] = field(default_factory=dict)
    #: `areas` / `notes` / `groups` → id → coordinates, or `null` to unplace it.
    layout: Mapping[str, Mapping[str, Sequence[float] | None]] = field(default_factory=dict)

    def validate(self) -> None:
        """Refuse a delta that names something the document has no such collection for.

        Refused rather than ignored: a typo in a collection name would otherwise be a write that
        reports success and changes nothing, which is the worst answer available.
        """
        for label, addressed in (("remove", self.remove), ("upsert", self.upsert)):
            unknown = sorted(set(addressed) - set(COLLECTIONS))
            if unknown:
                raise ScratchpadError(
                    f"{label} names {unknown}, which a scratchpad has no such collection for; "
                    f"it holds {list(COLLECTIONS)}"
                )
        unknown_layout = sorted(set(self.layout) - set(_PLACED))
        if unknown_layout:
            raise ScratchpadError(
                f"layout names {unknown_layout}; only {list(_PLACED)} carry geometry"
            )
        # The caller's own rows, deliberately — not the merged document, which also carries stored
        # ones. A scratchpad written by the older code may hold a destination this refuses, and
        # refusing it here would make the one edit that repairs it impossible.
        # The caller's own rows, deliberately — not the merged document, which also carries stored
        # ones. A scratchpad written by the older code may hold a destination this refuses, and
        # refusing it here would make the one edit that repairs it impossible.
        refuse_unknown_destinations(self.upsert.get("notes", ()))
        if not self.touches_anything():
            raise ScratchpadError("this edit changes nothing; say what to remove, upsert or place")

    def touches_anything(self) -> bool:
        return any(
            any(rows for rows in group.values())
            for group in (self.remove, self.upsert, self.layout)
        )


def _merged(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """RFC 7386 semantics, one nested level deep — which is as deep as a scratchpad row goes.

    `null` clears rather than stores: a document that carries `element-type: null` reads as a note
    that decided nothing, and `to_document` drops such keys anyway, so storing the null would be
    storing a value the next read would not return.
    """
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merged(merged[key], value)
        else:
            merged[key] = value
    return merged


def _rows(document: Mapping[str, Any], collection: str) -> list[dict[str, Any]]:
    raw: Any = document.get(collection) or []
    return [dict(row) for row in raw if isinstance(row, Mapping)]


def _upserted(
    document: dict[str, Any], collection: str, patches: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    rows = _rows(document, collection)
    index = {str(row.get("id")): position for position, row in enumerate(rows)}
    for patch in patches:
        row_id = str(patch.get("id") or "").strip()
        if not row_id:
            raise ScratchpadError(
                f"an upserted {collection[:-1]} needs an `id`; it says which one to change, "
                "and creates one when the scratchpad has no such id"
            )
        position = index.get(row_id)
        if position is None:
            index[row_id] = len(rows)
            rows.append(_merged({"id": row_id}, patch))
        else:
            rows[position] = _merged(rows[position], patch)
    return {**document, collection: rows}


def _layout_of(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    stored: Any = document.get("layout") or {}
    return {str(key): dict(value) for key, value in stored.items()}


def _placed(
    document: dict[str, Any], patch: Mapping[str, Mapping[str, Sequence[float] | None]]
) -> dict[str, Any]:
    layout = _layout_of(document)
    for collection, entries in patch.items():
        placements: dict[str, Any] = layout.get(collection, {})
        for row_id, coordinates in entries.items():
            if coordinates is None:
                placements.pop(row_id, None)
            else:
                placements[row_id] = list(coordinates)
        layout[collection] = placements
    return {**document, "layout": layout}


def apply_edit(stored: Scratchpad, edit: ScratchpadEdit) -> Scratchpad:
    """The stored scratchpad with the delta applied, validated as any other write is.

    Removals go through the aggregate where it has a method, because those methods own what a
    removal takes with it — restating the cascade here would give "remove a note" two meanings, one
    per surface. Areas and groups carry nothing but their own geometry, so they are dropped in the
    document, alongside the upserts and the placements which have no aggregate vocabulary at all.
    """
    edit.validate()

    working = stored
    for note_id in edit.remove.get("notes", ()):
        working = working.without_note(note_id)
    for link_id in edit.remove.get("links", ()):
        working = working.without_link(link_id)

    document = to_document(working)
    for collection in ("areas", "groups"):
        removing = set(edit.remove.get(collection, ()))
        if not removing:
            continue
        present = {str(row.get("id")) for row in _rows(document, collection)}
        missing = sorted(removing - present)
        if missing:
            raise ScratchpadError(f"no {collection[:-1]} {missing[0]!r} in this scratchpad")
        document[collection] = [
            row for row in _rows(document, collection) if str(row.get("id")) not in removing
        ]

    for collection in _PLACED:
        removing = set(edit.remove.get(collection, ()))
        placements = _layout_of(document).get(collection, {})
        if removing and placements:
            layout = _layout_of(document)
            layout[collection] = {k: v for k, v in placements.items() if k not in removing}
            document = {**document, "layout": layout}

    for collection in COLLECTIONS:
        patches = edit.upsert.get(collection, ())
        if patches:
            document = _upserted(document, collection, patches)

    if edit.layout:
        document = _placed(document, edit.layout)

    return from_document(document, artifact_id=stored.artifact_id)
