"""What a scratchpad document means when a *caller* sent it, rather than when a file held it.

`document.py` is the mapping, and it forgives: `parse_destination` degrades a value it does not
recognise, because the alternative is a file nobody can read. That is right for storage and wrong
for a request, whose sender can fix their input and is far better served by a sentence than by a
silent substitution.

So the two live apart, and are *named* apart. The obvious alternative — one parser with `strict=` —
would have put a boolean flag in the one place where getting the answer wrong is unrecoverable, and
left every caller deciding which rule applied to it.

The REST surface types its bodies, so pydantic refuses most of this before a handler runs. MCP does
not and cannot in the same way: its tools take JSON objects, so this is the boundary the agent
surface actually has — and the agent surface is where the value that caused all this came from.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.application.scratchpad.document import from_document
from src.domain.scratchpad import DESTINATIONS, Scratchpad, ScratchpadError


def refuse_unknown_destinations(rows: Iterable[Mapping[str, object]]) -> None:
    """A destination the caller invented is refused, naming the four that exist.

    Applied to the caller's own rows and never to a merged document, which is the distinction that
    matters: a merged document carries stored rows too, and refusing those would make a scratchpad
    that already holds a bad value impossible to edit — defending the damage instead of the caller.

    The message names `targets` because the field's *name* is what caused this. `destination` reads
    as "which project this lands in"; it is what the note becomes, and the model project a lift
    writes into is `targets` on `scratchpad_lift`, chosen per frame.
    """
    for row in rows:
        value = row.get("destination")
        if value is None or str(value) in DESTINATIONS:
            continue
        raise ScratchpadError(
            f"note {str(row.get('id') or '')!r} gives destination {str(value)!r}, which is not one "
            f"of {', '.join(DESTINATIONS)}. `destination` is what the note becomes; the model "
            "project it is lifted into is `targets` on scratchpad_lift, one per frame."
        )


def _note_rows(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = document.get("notes")
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


#: A frame's declaration, in the file's spelling and in the served one. `to_response` renames the
#: nested block into flat keys because the wire answers "what does this resolve to"; these two
#: resolve to themselves, so the served value *is* the declaration and reading it back is lossless.
#:
#: `permitted-element-types` is deliberately absent. It is the one served key that may be a
#: resolution — the element types of the frame's domains against the current ontology — and storing
#: a resolution would record an answer as though it were content, which is the thing `to_response`
#: exists to avoid. A caller narrowing element types outright says so with `permits.elements`.
_SERVED_DECLARATIONS = (("domains", "permitted-domains"), ("documents", "permitted-document-types"))


def _declared_permits(row: Mapping[str, object]) -> dict[str, object]:
    """What this frame declares, from whichever spelling the caller used. The nested block wins:
    it is the file's own, so a caller sending both is echoing a read it has since edited."""
    nested = row.get("permits")
    permits: dict[str, object] = dict(nested) if isinstance(nested, Mapping) else {}
    for key, served in _SERVED_DECLARATIONS:
        value = row.get(served)
        if not permits.get(key) and isinstance(value, list) and value:
            permits[key] = list(value)
    return permits


def _as_declaring_row(row: object) -> object:
    if not isinstance(row, Mapping):
        return row
    permits = _declared_permits(row)
    return {**row, "permits": permits} if permits else row


def _with_declared_permits(document: Mapping[str, Any]) -> dict[str, Any]:
    """The same document, with every frame's declaration in the spelling the file stores.

    Without this, the documented loop — "read it, edit it, hand it back" — *erased* what every frame
    declared: a read serves `permitted-domains`, the file stores `permits.domains`, and the reader
    knew only the second. The canvas hands back what it read on every save, so a seeded scratchpad
    lost the domains of its frames at the first drag, and its type picker then offered everything
    where it should have offered what the frame holds.
    """
    rows = document.get("areas")
    if not isinstance(rows, list):
        return dict(document)
    return {**document, "areas": [_as_declaring_row(row) for row in rows]}


def from_request_document(document: Mapping[str, Any], *, artifact_id: str) -> Scratchpad:
    """A whole document a caller sent: refused where `from_document` would heal, and read in the
    served vocabulary as well as the stored one, because a caller hands back what it was given."""
    refuse_unknown_destinations(_note_rows(document))
    return from_document(_with_declared_permits(document), artifact_id=artifact_id)
