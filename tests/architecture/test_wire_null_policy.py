"""The wire-null claim on a DTO, held against the routes that serialise it and the document.

``NullsOmitted`` is a claim a DTO makes about itself, and a claim nothing checked would be worse
than no claim: it is what makes the published document — and therefore the generated types the
frontend's decoders are verified against — say that an unset optional is *absent* rather than null.
If the claim and the routes drift apart, the document lies and the type-level contract check
certifies the lie.

So the biconditional is enforced in both directions. A marked DTO must be unreachable from any route
that would serialise its nulls; a DTO reachable only from null-omitting routes must be marked. That
leaves no third state to allowlist, and no shrink-only list to forget: the mixed case is derivable
rather than declared, because a DTO two routes serialise differently keeps the permissive default.
"""

from __future__ import annotations

import typing
from collections import defaultdict
from typing import Any

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.responses import Response

from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.rest.contracts.wire_nulls import WIRE_NULLS_KEYWORD, omits_nulls
from tests.support.route_introspection import api_routes


@pytest.fixture(scope="module")
def app() -> Any:
    return _build_app()


@pytest.fixture(scope="module")
def routes(app: Any) -> list[APIRoute]:
    return api_routes(app)


def _models_in(annotation: object) -> list[type[BaseModel]]:
    """Every model class the annotation mentions, at any depth of container or union."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in typing.get_args(annotation):
        found.extend(_models_in(argument))
    return found


def _reachable(model: type[BaseModel], seen: set[type[BaseModel]] | None = None) -> set[type[BaseModel]]:
    """``model`` and every model a field of it can carry — the schemas one response is built from.

    Transitive because ``exclude_none`` is: it drops None-valued keys at every level of the object
    it serialises, so a nested DTO is under the same policy as the one embedding it.
    """
    seen = set() if seen is None else seen
    if model in seen:
        return seen
    seen.add(model)
    for field in model.model_fields.values():
        for nested in _models_in(field.annotation):
            _reachable(nested, seen)
    return seen


def _response_model(route: APIRoute) -> type[BaseModel] | None:
    model = route.response_model
    return model if isinstance(model, type) and issubclass(model, BaseModel) else None


def _serialisation_policies(routes: list[APIRoute]) -> dict[type[BaseModel], set[bool]]:
    """Each response DTO → the set of ``exclude_none`` settings the routes serving it declare."""
    policies: dict[type[BaseModel], set[bool]] = defaultdict(set)
    for route in routes:
        model = _response_model(route)
        if model is None:
            continue
        for dto in _reachable(model):
            policies[dto].add(bool(route.response_model_exclude_none))
    return policies


def _returns_raw_response(route: APIRoute) -> bool:
    """Whether the handler returns a ``Response`` it built itself, bypassing ``response_model``."""
    try:
        returned = typing.get_type_hints(route.endpoint).get("return")
    except (NameError, TypeError):  # pragma: no cover - an unresolvable annotation is not a Response
        return False
    return isinstance(returned, type) and issubclass(returned, Response)


def _label(model: type[BaseModel]) -> str:
    return f"{model.__module__}.{model.__qualname__}"


def test_a_marked_dto_is_served_only_by_routes_that_omit_nulls(routes: list[APIRoute]) -> None:
    """The claim has to hold on every path that can produce the DTO, not on the one it was
    written for. A second route serving it without ``exclude_none`` sends the null the document
    now says is impossible, and the decoder built against that document rejects the row."""
    violations = {
        _label(model): sorted(
            f"{route.methods and sorted(route.methods)[0]} {route.path}"
            for route in routes
            if (served := _response_model(route)) is not None
            and model in _reachable(served)
            and not route.response_model_exclude_none
        )
        for model, policies in _serialisation_policies(routes).items()
        if omits_nulls(model) and False in policies
    }
    assert violations == {}, (
        "these DTOs declare NullsOmitted but are also served by routes that would send null:\n"
        + "\n".join(f"  {model}: {', '.join(where)}" for model, where in sorted(violations.items()))
    )


def test_a_dto_served_only_by_null_omitting_routes_declares_it(routes: list[APIRoute]) -> None:
    """The other direction, and the one that keeps the document honest as routes are added.

    A route declaring ``exclude_none`` while its DTO stays silent publishes a nullable optional it
    can never send. The generated type then carries ``| null``, and the only way to satisfy the
    contract check is to widen the decoder to accept a null — locking in the permissiveness the
    flag was added to remove.
    """
    unmarked = sorted(
        _label(model)
        for model, policies in _serialisation_policies(routes).items()
        if policies == {True} and not omits_nulls(model)
    )
    assert unmarked == [], (
        "every route serving these omits nulls, so they must derive from NullsOmitted for the "
        f"document to say so: {unmarked}"
    )


def test_no_marked_dto_is_also_a_request_body(routes: list[APIRoute]) -> None:
    """One schema serves both directions, and the policy is about serialisation only.

    A request body genuinely accepts an explicit ``null`` for a nullable field — that is validation,
    not serialisation — so stripping the null arm from a schema used as a body would understate what
    the surface accepts. Today no response DTO is also a body; this fails when that stops being true,
    rather than letting the document quietly narrow a request contract.
    """
    bodies: set[type[BaseModel]] = set()
    for route in routes:
        for parameter in route.dependant.body_params:
            for model in _models_in(parameter.field_info.annotation):
                bodies |= _reachable(model)
    marked_bodies = sorted(_label(model) for model in bodies if omits_nulls(model))
    assert marked_bodies == [], (
        "these are request bodies as well as null-omitting responses, so their schema cannot "
        f"carry the claim: {marked_bodies}"
    )


def test_no_route_declares_a_serialisation_policy_its_handler_bypasses(routes: list[APIRoute]) -> None:
    """A handler returning a ``Response`` it built itself is passed straight through: no validation
    against ``response_model``, and no ``exclude_none``/``exclude_unset``. The flag is then a
    statement about the document alone, which is exactly the divergence between schema and payload
    this surface exists to close — and it reads, to anyone maintaining the route, as though the
    server were doing something it is not."""
    ineffective = sorted(
        f"{route.operation_id or route.name} {route.path}"
        for route in routes
        if _returns_raw_response(route)
        and (route.response_model_exclude_none or route.response_model_exclude_unset)
    )
    assert ineffective == [], (
        "these declare a serialization flag their handler bypasses by returning a Response: "
        f"{ineffective}"
    )


def test_the_published_document_states_the_policy_rather_than_carrying_it(app: Any) -> None:
    """The keyword is scaffolding for generation, not part of the contract. A consumer that saw it
    would have to know what it meant; the point is that it does not have to."""
    document = app.openapi()
    schemas = (document.get("components") or {}).get("schemas") or {}
    assert [name for name, schema in schemas.items() if WIRE_NULLS_KEYWORD in schema] == []


def test_a_marked_dtos_optionals_are_published_as_absent_rather_than_nullable(
    app: Any, routes: list[APIRoute]
) -> None:
    """The transform's own regression: without it every assertion above can hold while the document
    still says ``string | null`` and the type-level check still cannot see the difference."""
    document = app.openapi()
    schemas = (document.get("components") or {}).get("schemas") or {}
    marked = {
        model.__name__
        for model in _serialisation_policies(routes)
        if omits_nulls(model)
    }
    assert marked, "no DTO declares the policy — this test would then assert nothing"
    nullable = {
        f"{name}.{field}"
        for name in marked
        for field, property_schema in (schemas.get(name, {}).get("properties") or {}).items()
        if {"type": "null"} in (property_schema.get("anyOf") or property_schema.get("oneOf") or [])
        or property_schema.get("type") == "null"
    }
    assert nullable == set(), f"published as nullable despite the policy: {sorted(nullable)}"
