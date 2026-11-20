"""A provisional reference is written by a plan and read by an applier — the pair, tested together.

Stated over what the form permits rather than over what a writer emits today: an alias is any text a
caller chose, so it may itself contain the prefix, a colon, or nothing at all.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from src.domain.provisional_reference import alias_of, name_in, provisional


@given(st.text())
def test_every_alias_survives_being_written_and_read_back(alias: str) -> None:
    assert alias_of(provisional(alias)) == alias
    assert name_in(provisional(alias)) == alias


def test_an_id_is_not_a_provisional_reference() -> None:
    assert alias_of("APP@1777293133.OYEmP1.architecture-backend") is None
    assert name_in("APP@1777293133.OYEmP1") == "APP@1777293133.OYEmP1"


def test_the_prefix_counts_only_at_the_start() -> None:
    """An id that merely contains the form is an id."""
    assert alias_of("x$ref:y") is None


def test_an_empty_alias_is_still_provisional() -> None:
    """Whether it resolves is the applier's refusal to make; reading it as an id would hide it."""
    assert alias_of(provisional("")) == ""
