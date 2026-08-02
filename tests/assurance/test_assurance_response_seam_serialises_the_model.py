"""The assurance response seam serialises the DTO it validated, not the payload it was handed.

`ok` and `_ok` are the only two places the assurance surface turns a payload into a response — twenty
call sites across ten router modules — because every response on this surface must carry `no-store`
itself, and FastAPI does not apply `response_model` to a `Response` a handler built. So the validation
and the serialisation the framework would have done happen at these two functions.

They used to do only half of that: validate the payload into a model object, discard it, and serialise
the *payload*. `model_validate` applies defaults into that object, so a field the handler omitted and
the DTO defaults was

* **present** in the published OpenAPI document,
* **present** in the generated TypeScript — `openapi-typescript` renders a defaulted *response* field
  as required, the server being understood always to send it — and
* **absent** on the wire.

Three of the four artefacts derived from one document agreed the field was required. That is the FMEA
defect precisely: the matrix handler emitted `dismissal: {}`, `FmeaCellDismissal` defaults both of its
fields, the client's decoder required both, and the entire matrix rendered blank with nothing logged.
It was fixed at that one producer, which left the seam — and nineteen other call sites reaching it.

This test is worth having even though the decoder-conformance harness would also catch it: this one
localises the fault to the seam, in the suite, with no running server and no browser.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from src.application.assurance import mutations
from src.infrastructure.rest.contracts.assurance_fmea import FmeaCellDismissal
from src.infrastructure.rest.contracts.wire_shape import Closed
from src.infrastructure.rest.routers.assurance._http import NO_STORE, ok
from src.infrastructure.rest.routers.assurance._write import _ok


class _Envelope(Closed):
    """A DTO shaped like the ones this surface serves: a required field and two defaulted ones."""

    identifier: str
    label: str = ""
    tags: list[str] = []  # noqa: RUF012 - pydantic copies a mutable default per instance


def _body(response: Any) -> dict[str, Any]:
    return json.loads(bytes(response.body).decode("utf-8"))


class TestTheReadSeam:
    def test_a_defaulted_field_the_handler_omitted_reaches_the_wire(self) -> None:
        body = _body(ok({"identifier": "N1"}, _Envelope))
        assert body == {"identifier": "N1", "label": "", "tags": []}

    def test_a_field_the_handler_supplied_is_not_overwritten_by_its_default(self) -> None:
        body = _body(ok({"identifier": "N1", "label": "Hazard", "tags": ["a"]}, _Envelope))
        assert body == {"identifier": "N1", "label": "Hazard", "tags": ["a"]}

    def test_the_fmea_dismissal_carries_both_of_its_fields(self) -> None:
        # The defect's own shape. `{}` is what the handler emitted for an undismissed cell, and it is
        # valid against the published JSON Schema — both fields have defaults, so neither is in
        # `required`. Which is why the JSON-Schema conformance walk reported it clean.
        body = _body(ok({"dismissal": {}}, _DismissalHolder))
        assert body == {"dismissal": {"by": "", "reason": ""}}

    def test_an_untyped_call_site_still_passes_its_payload_through(self) -> None:
        # Some call sites serve a genuinely dynamic map and pass no model. They must keep working, and
        # they get no guarantee — which is the argument for there being few of them.
        body = _body(ok({"anything": {"at": "all"}}))
        assert body == {"anything": {"at": "all"}}

    def test_the_confidentiality_header_survives_the_change(self) -> None:
        for response in (ok({"identifier": "N1"}, _Envelope), ok({"x": 1})):
            assert response.headers["Cache-Control"] == NO_STORE


class _DismissalHolder(Closed):
    dismissal: FmeaCellDismissal


class TestTheWriteSeam:
    def test_a_defaulted_field_the_handler_omitted_reaches_the_wire(self) -> None:
        result = mutations.MutationOk(payload={"identifier": "N1"})
        assert _body(_ok(result, _Envelope)) == {"identifier": "N1", "label": "", "tags": []}

    def test_verification_findings_ride_along_when_the_write_produced_them(self) -> None:
        # The one key `_ok` adds that no handler puts in its payload, so it is the one the DTO has to
        # declare for the serialisation to keep it. It used to survive by accident: the payload was
        # what got serialised, so an undeclared key would have reached the client regardless.
        result = mutations.MutationOk(
            payload={"identifier": "N1"}, findings=[{"code": "E1", "message": "advisory"}]
        )
        body = _body(_ok(result, _FindingsEnvelope))
        assert body["verification_findings"] == [{"code": "E1", "message": "advisory"}]

    def test_findings_are_null_rather_than_absent_when_the_write_produced_none(self) -> None:
        # The DTO declares the key with a `None` default, and the generated client type therefore
        # carries it. Absence was the third of the three ways this surface disagreed with its own
        # document; null is what the document says.
        body = _body(_ok(mutations.MutationOk(payload={"identifier": "N1"}), _FindingsEnvelope))
        assert body["verification_findings"] is None

    def test_the_confidentiality_header_survives_the_change(self) -> None:
        result = mutations.MutationOk(payload={"identifier": "N1"})
        assert _ok(result, _Envelope).headers["Cache-Control"] == NO_STORE


class _FindingsEnvelope(Closed):
    identifier: str
    verification_findings: list[dict[str, Any]] | None = None


def test_every_dto_this_surface_serves_is_closed() -> None:
    """The serialisation is only faithful if the DTO is the whole contract.

    An open DTO would let a key the document does not declare through `model_validate` and then drop
    it in `model_dump` — silently narrowing the body rather than reporting the divergence. Closedness
    is what makes the seam's refusal the loud outcome.
    """
    for model in (_Envelope, _FindingsEnvelope, _DismissalHolder, FmeaCellDismissal):
        assert issubclass(model, BaseModel)
        assert model.model_config.get("extra") == "forbid", model.__name__
