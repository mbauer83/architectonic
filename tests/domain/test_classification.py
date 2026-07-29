"""Unit tests for the TLP classification ordering and publishability boundary."""

from __future__ import annotations

import pytest

from src.domain.assurance.classification import (
    PUBLISHABLE_CEILING,
    TLP_AMBER,
    TLP_GREEN,
    TLP_ORDER,
    TLP_RED,
    TLP_WHITE,
    is_publishable,
    normalize_tlp,
    tlp_rank,
)


def test_order_is_ascending_sensitivity() -> None:
    assert TLP_ORDER == (TLP_WHITE, TLP_GREEN, TLP_AMBER, TLP_RED)
    assert tlp_rank(TLP_WHITE) < tlp_rank(TLP_GREEN) < tlp_rank(TLP_AMBER) < tlp_rank(TLP_RED)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(TLP_WHITE, True), (TLP_GREEN, True), (TLP_AMBER, False), (TLP_RED, False)],
)
def test_publishable_boundary_at_green(value: str, expected: bool) -> None:
    assert is_publishable(value) is expected


def test_publishable_ceiling_is_green() -> None:
    assert PUBLISHABLE_CEILING == TLP_GREEN


def test_normalize_is_case_and_whitespace_insensitive() -> None:
    assert normalize_tlp("  tlp:green ") == TLP_GREEN


def test_unknown_or_blank_defaults_to_conservative_confidential() -> None:
    # Unclassified / malformed content is treated as confidential (AMBER), not publishable.
    assert normalize_tlp(None) == TLP_AMBER
    assert normalize_tlp("nonsense") == TLP_AMBER
    assert is_publishable(None) is False
    assert is_publishable("") is False
