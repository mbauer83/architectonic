"""A field the bulk decoder accepts reaches the write function. All of them, not most.

`KNOWN_ITEM_FIELDS` refuses an item carrying a field its operation does not accept, and the comment
above it records why: an `edit_connection` carrying `mode: "remove"` — the field is `operation` — ran
as an update and reported `wrote: true` for a removal that never happened. Silently doing something
other than what was asked is the failure that whitelist exists to prevent.

Accepting a field and then not applying it is the same failure with the same symptom. It was live:
`edit_connection` accepted `specializations` and `metadata`, `edit_connection` in the write path takes
both, and the decoder passed neither — so a caller setting a connection's specializations was told
`wrote: true` and got no change.

The whitelist could not catch it, because validation and application were derived from different
places: one from the catalogue, the other from a hand-written ladder of `item["x"] if "x" in item`.
This asserts they agree, per operation and per field, so a field added to one and not the other fails
here rather than being reported by whoever needed it.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.application.modeling import edit_field_catalogue as catalogue
from src.infrastructure.mcp.artifact_mcp.bulk import write_apply
from src.infrastructure.mcp.artifact_mcp.bulk.common import KNOWN_ITEM_FIELDS

#: The envelope and the mode selector are the decoder's own; they never reach a write function.
_NOT_A_FIELD = frozenset({"op", "_ref", "operation"})

_A_VALUE: Any = {"probe": ["value"]}


def _item(op: str) -> dict[str, Any]:
    """An item carrying every field its operation accepts, so nothing is covered by omission."""
    return {"op": op} | {
        field: _A_VALUE for field in KNOWN_ITEM_FIELDS[op] - _NOT_A_FIELD
    }


@pytest.fixture()
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """What each write function was called with, instead of writing anything."""
    seen: dict[str, dict[str, Any]] = {}

    def record(name: str):
        def call(**kwargs: Any) -> object:
            seen[name] = kwargs
            return object()
        return call

    for name in ("edit_entity", "edit_connection", "remove_connection"):
        monkeypatch.setattr(write_apply.artifact_write_ops, name, record(name))
    monkeypatch.setattr(write_apply, "expand_artifact_id", lambda _registry, value: value)
    return seen


@pytest.mark.parametrize(
    ("op", "writer"), [("edit_entity", "edit_entity"), ("edit_connection", "edit_connection")]
)
def test_every_accepted_field_reaches_the_write_function(
    op: str, writer: str, captured: dict[str, dict[str, Any]], tmp_path
) -> None:
    write_apply._apply_single_edit(
        item=_item(op), op=op, registry=None, verifier=None,  # type: ignore[arg-type]
        clear_repo_caches=lambda _: None, staged_root=tmp_path,
    )

    accepted = KNOWN_ITEM_FIELDS[op] - _NOT_A_FIELD
    dropped = sorted(accepted - set(captured[writer]))
    assert dropped == [], (
        f"`{op}` accepts {dropped} and does not pass {'it' if len(dropped) == 1 else 'them'} to "
        f"`{writer}`. A field accepted and not applied reports `wrote: true` for a change that "
        "never happened, which is what the accepted-field whitelist exists to prevent."
    )


@pytest.mark.parametrize("kind", ["entity", "connection"])
def test_the_decoder_and_the_catalogue_name_the_same_fields(kind: str) -> None:
    """The precondition for the assertion above: both sides are derived from one declaration."""
    op = f"edit_{kind}"
    assert KNOWN_ITEM_FIELDS[op] - _NOT_A_FIELD == catalogue.editable(kind)  # type: ignore[arg-type]
