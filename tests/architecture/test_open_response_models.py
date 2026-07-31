"""Only the rostered models and fields accept undeclared keys, and the temporary entries cannot outlive
their work.

`extra="allow"` publishes `additionalProperties: true` — "an object", promising nothing. Closing those
is Phase 1 §0e's work, and a handful of shapes are legitimately open because their schema belongs to
someone else. `contracts/open_models.py` is the roster; these tests are what make it a count rather
than a comment.

Two of them earn their place by having already found something. The roster keyed by *base class* passed
while `AssuranceNodeRecord` and `AffectedEntity` were open by inheriting `_FeedShaped`, neither being a
feed row — openness had been acquired by attaching the nearest base, and the reason in that base's
docstring was false of both. Keying by concrete model is what turned that from invisible into one line
of review each.

**Reading `model_config` was not enough, and that gap was load-bearing.** These tests asked each model
whether it allowed extras, so they saw nothing wrong with `WriteResultResponse` — `extra="forbid"`, a
docstring that says "closed" — while its `verification: dict[str, Any]` published
`additionalProperties: true` on every mutation response the surface serves. A client reading the schema
was told a write returns "an object". The checks therefore work from the **published schema** now, where
the two forms are the same defect at different depths: `additionalProperties: true` on a schema is an
open model, and the same keyword inside one of its properties is an open field.
"""

from __future__ import annotations

import typing
from typing import Any

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.gui.contracts.open_models import (
    AWAITING_CONTRACT,
    OPEN_RESPONSE_FIELDS,
    OPEN_RESPONSE_MODELS,
    PENDING_DECISION,
)
from src.infrastructure.gui.route_policy import BY_KEY, UNTYPED_RESPONSE_OPERATIONS
from tests.support.route_introspection import api_routes


@pytest.fixture(scope="module")
def app() -> Any:
    return _build_app()


@pytest.fixture(scope="module")
def routes(app: Any) -> list[APIRoute]:
    return api_routes(app)


def _models_in(annotation: object) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in typing.get_args(annotation):
        found.extend(_models_in(argument))
    return found


def _reachable(model: type[BaseModel], seen: set[type[BaseModel]] | None = None) -> set[type[BaseModel]]:
    """``model`` and every model a field of it can carry.

    Transitive, because openness is a property of what a client decodes: a nested open row makes the
    response as unpredictable as an open envelope would.
    """
    seen = set() if seen is None else seen
    if model in seen:
        return seen
    seen.add(model)
    for field in model.model_fields.values():
        for nested in _models_in(field.annotation):
            _reachable(nested, seen)
    return seen


def _operation_ids(route: APIRoute) -> set[str]:
    """The manifest's operation ids for this route.

    From the manifest by ``(method, template)``, not from ``route.operation_id`` — which is ``None`` on
    the route object, because the id is applied by ``generate_unique_id_function`` when the document is
    generated. Taking the handler's function name instead compares names against manifest ids and
    matches nothing, which is how this test first reported an empty result.
    """
    return {
        row.operation_id
        for method in (route.methods or set())
        if (row := BY_KEY.get((method.upper(), route.path))) is not None
    }


#: Keywords that annotate a schema without constraining what validates against it. A sub-schema carrying
#: only these — which is what a field annotated `Any` generates — accepts anything, exactly as
#: `additionalProperties: true` does.
_ANNOTATION_ONLY = frozenset(
    {"title", "description", "default", "examples", "deprecated", "readOnly", "writeOnly"}
)


def _accepts_anything(schema: object) -> bool:
    """Whether ``schema`` constrains nothing — an arbitrary object, or an arbitrary value.

    Recurses through the composition keywords, so `list[dict[str, Any]]` and
    `dict[str, dict[str, Any]]` are found as readily as the bare map: a client decoding an array of
    arbitrary objects knows no more than one decoding a single one. `$ref` is deliberately *not*
    followed — the referenced model is reached separately, carrying its own name, and following the ref
    would report the defect against whichever model happened to embed it.
    """
    if schema is True:
        return True
    if not isinstance(schema, dict):
        return False
    if schema.get("additionalProperties") is True:
        return True
    if not set(schema) - _ANNOTATION_ONLY:
        return True
    if any(_accepts_anything(schema.get(key)) for key in ("items", "additionalProperties")):
        return True
    return any(
        isinstance(arms := schema.get(key), list) and any(_accepts_anything(arm) for arm in arms)
        for key in ("anyOf", "oneOf", "allOf", "prefixItems")
    )


def _served_open_models(routes: list[APIRoute]) -> dict[str, set[str]]:
    """Each open model actually served → the operation ids serving it."""
    by_model: dict[str, set[str]] = {}
    for route in routes:
        for declared in _models_in(route.response_model):
            for model in _reachable(declared):
                if _accepts_anything(model.model_json_schema()):
                    by_model.setdefault(model.__name__, set()).update(_operation_ids(route))
    return by_model


def _served_open_fields(routes: list[APIRoute]) -> dict[str, set[str]]:
    """Each ``Model.field`` whose *type* publishes an arbitrary object → the operation ids serving it.

    Only a model's own properties are examined. Every nested model is in the reachable set on its own
    account, so its fields are reported under its own name rather than under a path through whatever
    embedded it — which keeps a roster key stable when a shape gains a second consumer.
    """
    by_field: dict[str, set[str]] = {}
    for route in routes:
        for declared in _models_in(route.response_model):
            for model in _reachable(declared):
                properties = model.model_json_schema().get("properties") or {}
                for name, property_schema in properties.items():
                    if _accepts_anything(property_schema):
                        key = f"{model.__name__}.{name}"
                        by_field.setdefault(key, set()).update(_operation_ids(route))
    return by_field


def test_the_surface_serves_open_models_at_all(routes: list[APIRoute]) -> None:
    """Guards the guard. Every assertion below is over the served set, so an extraction that found
    nothing would satisfy all of them — which is exactly what the first version of this file did."""
    assert _served_open_models(routes), "found no open models at all; the extraction is broken"


def test_every_open_model_served_is_on_the_roster(routes: list[APIRoute]) -> None:
    served = _served_open_models(routes)
    undeclared = {name: sorted(ops) for name, ops in served.items() if name not in OPEN_RESPONSE_MODELS}
    assert undeclared == {}, (
        "these publish undeclared fields to clients with nothing recording why. Close the model, or add "
        "it to contracts/open_models.py with its reason:\n"
        + "\n".join(f"  {name}: {ops}" for name, ops in sorted(undeclared.items()))
    )


def test_every_roster_entry_is_actually_served(routes: list[APIRoute]) -> None:
    """The other direction, so the roster describes the surface instead of aspiring to it."""
    unserved = sorted(set(OPEN_RESPONSE_MODELS) - set(_served_open_models(routes)))
    assert unserved == [], (
        f"rostered but not served: {unserved}. Remove the entry — a standing exception for something "
        "that no longer exists is how the next one gets waved through."
    )


def test_the_surface_serves_open_fields_at_all(routes: list[APIRoute]) -> None:
    """Guards the field-level guard the same way, and for the same reason: an extraction that found
    nothing would satisfy both assertions below."""
    assert _served_open_fields(routes), "found no open fields at all; the extraction is broken"


def test_every_open_field_served_is_on_the_roster(routes: list[APIRoute]) -> None:
    """The check `WriteResultResponse.verification` needed. A closed model carrying a `dict[str, Any]`
    publishes the same `additionalProperties: true` an open model does, one level down, and reads as
    closed everywhere a reviewer would look."""
    served = _served_open_fields(routes)
    undeclared = {name: sorted(ops) for name, ops in served.items() if name not in OPEN_RESPONSE_FIELDS}
    assert undeclared == {}, (
        "these publish an arbitrary object to clients from inside a closed model, with nothing recording "
        "why. Give the field a type, or add it to contracts/open_models.py with its reason:\n"
        + "\n".join(f"  {name}: {ops}" for name, ops in sorted(undeclared.items()))
    )


def test_every_rostered_field_is_actually_served(routes: list[APIRoute]) -> None:
    """The other direction. A field that has since been typed leaves a standing exception behind it, and
    the next open field then lands next to an entry nobody re-read."""
    unserved = sorted(set(OPEN_RESPONSE_FIELDS) - set(_served_open_fields(routes)))
    assert unserved == [], (
        f"rostered but not served: {unserved}. Remove the entry — either the field is typed now, or it "
        "was renamed and the roster is describing something that no longer exists."
    )


def test_the_placeholder_is_served_only_by_operations_awaiting_a_contract(
    routes: list[APIRoute],
) -> None:
    """Otherwise a drained route could quietly regain an open body, and it would not appear as a new
    open model — only as a reused one, which no review notices."""
    placeholders = [
        name for name, reason in OPEN_RESPONSE_MODELS.items() if reason == AWAITING_CONTRACT
    ]
    served = _served_open_models(routes)
    leaked = sorted(
        operation
        for name in placeholders
        for operation in served.get(name, set())
        if operation not in UNTYPED_RESPONSE_OPERATIONS
    )
    assert leaked == [], (
        f"these serve the migration placeholder without being listed as awaiting a contract: {leaked}"
    )


def test_nothing_temporary_outlives_the_work_that_removes_it() -> None:
    """The exit condition as a test rather than a note.

    `awaiting-contract` and `pending-decision` are both promises to come back. An empty operation ledger
    with the placeholder still rostered would leave the surface permanently able to answer with an
    arbitrary object — the outcome this phase exists to prevent, reached by finishing the work and
    forgetting the note.

    Fields count too. "Every operation typed" is not reached while a typed operation's response still
    contains an object nobody described; a per-operation ledger cannot see that, and this can.
    """
    if UNTYPED_RESPONSE_OPERATIONS:
        pytest.skip(
            f"{len(UNTYPED_RESPONSE_OPERATIONS)} operations still await a response contract"
        )
    temporary = sorted(
        name
        for roster in (OPEN_RESPONSE_MODELS, OPEN_RESPONSE_FIELDS)
        for name, reason in roster.items()
        if reason in (AWAITING_CONTRACT, PENDING_DECISION)
    )
    assert temporary == [], (
        f"the drain is finished but these are still open on a temporary reason: {temporary}"
    )
