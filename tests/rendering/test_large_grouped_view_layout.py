"""A large boxed view must not hand GraphViz something it throws on.

A 35-node ArchiMate view across 7 `authored_groupings` boxes made PlantUML answer with a page of
Java stack trace where the picture should be — `IllegalStateException` out of
`DotStringFactory.solve` — while the write reported `verification.valid: true` and buried the crash
in `warnings`. Bisected against the repo's own `plantuml.jar`: removing only the `-[hidden]` ordering
lines renders the same view in about two seconds.

Nothing caught it because every rendering test uses a handful of entities, and the hidden chains are
free at that size. So this asserts the *shape* at scale rather than rendering: above the budget the
generator must stop emitting them, and below it must keep them, because they are what makes a small
boxed view read in a sensible order.
"""

from __future__ import annotations

from src.infrastructure.rendering._authored_grouping_rendering import (
    _HIDDEN_CHAIN_MEMBER_BUDGET,
    _member_count,
)


class _Group:
    """The shape `_member_count` walks: members plus nested subgroups."""

    def __init__(self, members: int, subgroups: list["_Group"] | None = None) -> None:
        self.members = [object()] * members
        self.subgroups = subgroups or []


def test_members_are_counted_through_nesting() -> None:
    """A budget that only counted the top level would miss exactly the deep views that crash."""
    tree = [_Group(3, [_Group(4), _Group(2, [_Group(5)])]), _Group(1)]

    assert _member_count(tree) == 15  # type: ignore[arg-type]


def test_the_budget_sits_above_an_ordinary_boxed_view_and_below_the_one_that_crashed() -> None:
    """Both directions matter: too low and every small view loses its ordering for nothing, too
    high and the crash is still reachable. The observed failure was 35 members over 7 boxes."""
    ordinary = _member_count([_Group(4), _Group(3), _Group(5)])  # type: ignore[arg-type]
    crashed = _member_count([_Group(5) for _ in range(7)])  # type: ignore[arg-type]

    assert ordinary <= _HIDDEN_CHAIN_MEMBER_BUDGET, "a small boxed view keeps its ordering"
    assert crashed > _HIDDEN_CHAIN_MEMBER_BUDGET, "the view that crashed GraphViz drops the chains"
