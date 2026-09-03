"""`to_mapping` and `standing_from_mapping` are a pair, and the pair is what is tested.

The project has paid three times for a syntax with two readers that disagreed, and the gate that
caught the third was a round trip stated over what the encoding *permits* — not over what the writer
happens to emit. So the generated cases below cover every arm, every condition, multi-proposal and
multi-field standings, and the refusals cover encodings a client could produce that the writer never
would.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.baseline_standing import (
    BASELINE,
    BASELINE_KIND,
    CHANGE_CONDITIONS,
    PROPOSED_KIND,
    EnterpriseBaseline,
    ImpossibleStanding,
    Proposed,
    standing_from_mapping,
)

_ids = st.lists(st.text(min_size=1, max_size=12).filter(str.strip), min_size=1, max_size=4)
_fields = st.lists(st.sampled_from(["name", "description", "status", "keywords", "body"]), min_size=1, max_size=5)

_proposed = st.builds(
    Proposed,
    proposal_ids=_ids.map(tuple),
    changed_fields=_fields.map(tuple),
    base_revision=st.text(min_size=1, max_size=40).filter(str.strip),
    condition=st.sampled_from(CHANGE_CONDITIONS),
)
_standings = st.one_of(st.just(EnterpriseBaseline()), _proposed)


@settings(max_examples=200, deadline=None)
@given(_standings)
def test_every_permitted_standing_survives_the_round_trip(standing) -> None:
    assert standing_from_mapping(standing.to_mapping()) == standing


def test_both_arms_are_reachable_from_the_generator() -> None:
    """Precondition: a strategy that only ever produced one arm would make the property vacuous."""
    seen = {type(standing_from_mapping(s.to_mapping())) for s in (EnterpriseBaseline(), _example())}
    assert seen == {EnterpriseBaseline, Proposed}


def test_the_two_arms_do_not_encode_to_the_same_kind() -> None:
    assert EnterpriseBaseline().to_mapping()["kind"] == BASELINE_KIND
    assert _example().to_mapping()["kind"] == PROPOSED_KIND


def test_the_shared_baseline_value_is_the_baseline_arm() -> None:
    assert BASELINE == EnterpriseBaseline()
    assert standing_from_mapping(BASELINE.to_mapping()) == BASELINE


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"kind": "unknown-kind"},
        {"kind": ""},
        {"kind": "Proposed"},
        {"kind": None},
    ],
)
def test_an_unrecognised_kind_is_refused_rather_than_read_as_baseline(payload) -> None:
    """The dangerous default: reading an unknown encoding as the baseline makes a proposal invisible."""
    with pytest.raises(ImpossibleStanding):
        standing_from_mapping(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": PROPOSED_KIND},
        {"kind": PROPOSED_KIND, "proposal_ids": [], "changed_fields": ["name"], "base_revision": "r"},
        {"kind": PROPOSED_KIND, "proposal_ids": ["p"], "changed_fields": [], "base_revision": "r"},
        {"kind": PROPOSED_KIND, "proposal_ids": ["p"], "changed_fields": ["name"], "base_revision": ""},
        {"kind": PROPOSED_KIND, "proposal_ids": "p", "changed_fields": ["name"], "base_revision": "r"},
        {"kind": PROPOSED_KIND, "proposal_ids": ["p"], "changed_fields": ["name"], "base_revision": "r", "condition": "fine"},
    ],
)
def test_a_proposed_encoding_missing_what_makes_it_reviewable_is_refused(payload) -> None:
    with pytest.raises(ImpossibleStanding):
        standing_from_mapping(payload)


def test_a_condition_absent_from_the_encoding_is_refused_not_assumed_current() -> None:
    """`current` is the harmless-looking guess, and guessing it hides a stale proposal."""
    with pytest.raises(ImpossibleStanding):
        standing_from_mapping(
            {"kind": PROPOSED_KIND, "proposal_ids": ["p"], "changed_fields": ["name"], "base_revision": "r"}
        )


@pytest.mark.parametrize("condition", CHANGE_CONDITIONS)
def test_every_declared_condition_is_constructible_and_survives(condition) -> None:
    """Enumerating a closed set and getting it wrong is the failure this pins."""
    standing = Proposed(("PCH@1.x",), ("name",), "abc123", condition)
    assert standing_from_mapping(standing.to_mapping()) == standing


@pytest.mark.parametrize(
    "kwargs",
    [
        {"proposal_ids": (), "changed_fields": ("name",), "base_revision": "r", "condition": "current"},
        {"proposal_ids": ("p",), "changed_fields": (), "base_revision": "r", "condition": "current"},
        {"proposal_ids": ("p",), "changed_fields": ("name",), "base_revision": "", "condition": "current"},
        {"proposal_ids": ("p",), "changed_fields": ("name",), "base_revision": "r", "condition": "nope"},
    ],
)
def test_the_constructor_refuses_the_same_shapes_the_decoder_does(kwargs) -> None:
    """One refusal vocabulary, so a value cannot exist that its own encoding could not be read back."""
    with pytest.raises(ImpossibleStanding):
        Proposed(**kwargs)


def test_a_proposed_standing_renders_which_fields_for_the_cli() -> None:
    """The CLI is `print(record)`, so a standing reaches it only by rendering — and D5 asks *which*."""
    rendered = str(Proposed(("PCH@1.abc",), ("name", "description"), "9f2c", "stale"))
    assert "name" in rendered and "description" in rendered
    assert "PCH@1.abc" in rendered
    assert "stale" in rendered


def test_the_baseline_renders_without_ceremony() -> None:
    assert str(EnterpriseBaseline()) == "enterprise baseline"


def test_a_current_proposal_does_not_render_a_condition_nobody_asked_about() -> None:
    assert "current" not in str(Proposed(("p",), ("name",), "r", "current"))


def _example() -> Proposed:
    return Proposed(("PCH@1.abc",), ("name",), "9f2c", "current")
