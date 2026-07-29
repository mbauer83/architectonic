"""Binding an enum-set parameter to a request: canonicalization, default application, and the
typed errors (scalar-where-array, unknown member, below-min-items)."""

from __future__ import annotations

import pytest

from src.application.viewpoints.parameter_binding import ViewpointParameterError, bind_parameters
from src.domain.viewpoints.viewpoint_bindings import QueryParameter
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery
from tests.application.viewpoints._fixtures import Store

_ALLOWED = ("goal", "outcome", "requirement")


def _query(**over: object) -> ExecutableViewpointQuery:
    defaults: dict[str, object] = dict(
        name="scope", value_type="string", cardinality="many", allowed_values=_ALLOWED, min_items=1, required=True,
    )
    defaults.update(over)
    return ExecutableViewpointQuery(parameters=(QueryParameter(**defaults),))  # type: ignore[arg-type]


def _bind(query: ExecutableViewpointQuery, supplied: dict) -> dict:
    return bind_parameters(query, supplied, Store())


class TestEnumSetBinding:
    def test_canonicalizes_to_declaration_order(self) -> None:
        resolved = _bind(_query(), {"scope": ["requirement", "goal", "goal"]})
        assert resolved["scope"] == ("goal", "requirement")

    def test_reordering_binds_identically(self) -> None:
        a = _bind(_query(), {"scope": ["requirement", "goal"]})
        b = _bind(_query(), {"scope": ["goal", "requirement"]})
        assert a == b

    def test_default_applied_when_omitted(self) -> None:
        resolved = _bind(_query(default=("goal", "outcome")), {})
        assert resolved["scope"] == ("goal", "outcome")

    def test_scalar_where_array_rejected(self) -> None:
        with pytest.raises(ViewpointParameterError) as exc:
            _bind(_query(), {"scope": "goal"})
        assert exc.value.code == "parameter-not-a-set"

    def test_unknown_member_rejected(self) -> None:
        with pytest.raises(ViewpointParameterError) as exc:
            _bind(_query(), {"scope": ["goal", "bogus"]})
        assert exc.value.code == "set-parameter-unknown-member"

    def test_below_min_items_rejected(self) -> None:
        with pytest.raises(ViewpointParameterError) as exc:
            _bind(_query(min_items=2), {"scope": ["goal"]})
        assert exc.value.code == "set-parameter-below-min-items"

    def test_empty_set_rejected_as_below_min(self) -> None:
        with pytest.raises(ViewpointParameterError) as exc:
            _bind(_query(), {"scope": []})
        assert exc.value.code == "set-parameter-below-min-items"
