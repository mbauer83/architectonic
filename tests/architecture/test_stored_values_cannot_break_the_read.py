"""No value a scratchpad can hold may be one its response contract refuses to serve.

The enum on `NoteWire.destination` was enforced in exactly one place — on the way *out* — where the
only thing it can do is fail. The domain took the same `Literal` on trust, because Python does not
check one at runtime, so a value that broke it was stored happily and then made every read of that
scratchpad a 500, permanently.

The rule is one-directional and worth stating plainly: **the wire contract may only ever restate
what the domain already guarantees.** A contract that constrains more than the domain does is not a
stricter contract, it is a latent 500 — and it fails on read, long after and far from the write that
caused it.

This is written by reflection rather than as a list, so it covers the `Literal` nobody has added
yet. `tests/infrastructure/test_scratchpad_destination_contract.py` holds the behaviour; this holds
the property that made the behaviour possible to get wrong.
"""

from __future__ import annotations

from typing import Literal, get_args, get_origin

import pytest

from src.application.scratchpad.document import from_document, to_response
from src.infrastructure.rest.contracts.scratchpads import NoteWire, ScratchpadResponse

_ARTIFACT_ID = "SCR@1786299627.aaaaaa.a-canvas"

#: A value no enum will ever contain, and the shape of the one that actually caused this: a
#: plausible-looking slug an agent supplied for a field whose name invited it.
_HOSTILE = "up2parts-autocam"


def _registry() -> object:
    from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

    return build_module_registry(complete_vocabulary=True)


def _literal_fields() -> list[str]:
    """Every field of `NoteWire` the contract pins to a closed set of values."""
    return [
        name
        for name, info in NoteWire.model_fields.items()
        if get_origin(info.annotation) is Literal
        or any(get_origin(arg) is Literal for arg in get_args(info.annotation))
    ]


def _document(**note_overrides: object) -> dict[str, object]:
    return {
        "artifact-id": _ARTIFACT_ID,
        "artifact-type": "scratchpad",
        "name": "A canvas",
        "version": "0.1.0",
        "status": "draft",
        "meta-ontology": "archimate-4",
        "areas": [{"id": "strategy", "label": "Vision & strategy"}],
        "notes": [{"id": "n1", "title": "A thought", **note_overrides}],
    }


def test_the_scan_finds_the_fields_it_means_to() -> None:
    """Without this, a reflection that matched nothing would report every field safe."""
    fields = _literal_fields()

    assert "destination" in fields, fields


def test_a_note_the_domain_accepts_is_a_note_the_contract_can_serve() -> None:
    """The baseline: an ordinary document round-trips."""
    scratchpad = from_document(_document(destination="element", **{"element-type": "goal"}))

    ScratchpadResponse.model_validate(
        to_response(scratchpad, group="platform-core", registry=_registry())
    )


@pytest.mark.parametrize("field", _literal_fields())
def test_no_stored_value_of_a_closed_field_can_make_the_read_fail(field: str) -> None:
    """Whatever is on disk, the read answers.

    Parametrized by reflection so a `Literal` added to the contract tomorrow is covered the day it
    is added — which is the only way this stays true, since the failure appears on an unrelated
    read and names a note the caller cannot look up.
    """
    document = _document(**{field.replace("_", "-"): _HOSTILE})

    scratchpad = from_document(document)
    served = to_response(scratchpad, group="platform-core", registry=_registry())

    # The value degrades; what it must not do is make the document unreadable.
    ScratchpadResponse.model_validate(served)
