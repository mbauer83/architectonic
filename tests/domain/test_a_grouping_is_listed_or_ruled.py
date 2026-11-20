"""A grouping holds the members it lists or the ones a rule selects.

A listed grouping claims first, then the most specific rule.
"""

from __future__ import annotations

from src.domain.diagrams.authored_groupings import (
    check_groupings,
    grouping_ids,
    states_a_ruled_grouping,
    with_grouping_ids,
)
from src.domain.diagrams.grouping_membership import DrawingTraits, Placement, place_in_groupings

#: drawing → (domain, type)
_DRAWN = {
    "clerk": ("business", "business-actor"),
    "desk": ("business", "business-service"),
    "claims": ("business", "business-service"),
    "portal": ("application", "application-component"),
    "ledger": ("application", "application-component"),
    "events": ("application", "application-event"),
    "host": ("technology", "node"),
}
_TRAITS = DrawingTraits[str](domain_of=lambda name: _DRAWN[name][0], type_of=lambda name: _DRAWN[name][1])


def _placed(groupings: list[dict[str, object]]) -> Placement[str]:
    return place_in_groupings(groupings, drawings=list(_DRAWN), named=lambda name: name if name in _DRAWN else None,
                              traits=_TRAITS)


def _members(placement: Placement[str]) -> dict[str, tuple[str, ...]]:
    return {str(group.declaration["label"]): group.members for group in placement.every_grouping()}


def test_a_listed_grouping_holds_what_it_names_and_nothing_else() -> None:
    placement = _placed([{"label": "Front", "entity-ids": ["portal", "clerk", "nobody"]}])

    assert _members(placement) == {"Front": ("portal", "clerk")}
    assert placement.unclaimed == ("desk", "claims", "ledger", "events", "host")


def test_a_drawing_is_in_the_first_listed_grouping_that_names_it() -> None:
    placement = _placed([
        {"label": "First", "entity-ids": ["portal"]},
        {"label": "Second", "entity-ids": ["portal", "ledger"]},
    ])

    assert _members(placement) == {"First": ("portal",), "Second": ("ledger",)}


def test_a_ruled_grouping_holds_what_its_rule_admits_of_what_is_left() -> None:
    placement = _placed([
        {"label": "Front", "entity-ids": ["portal"]},
        {"label": "Application", "rule": {"domain": "application"}},
    ])

    assert _members(placement) == {"Front": ("portal",), "Application": ("ledger", "events")}


def test_a_member_settles_in_the_most_specific_rule() -> None:
    placement = _placed([
        {"label": "Application", "rule": {"domain": "application"},
         "groups": [{"label": "Components", "rule": {"type": "application-component"}}]},
    ])

    assert _members(placement) == {"Application": ("events",), "Components": ("portal", "ledger")}


def test_between_sibling_rules_a_type_outranks_a_domain_whatever_the_order() -> None:
    placement = _placed([
        {"label": "Business", "rule": {"domain": "business"}},
        {"label": "Services", "rule": {"type": "business-service"}},
    ])

    assert _members(placement) == {"Business": ("clerk",), "Services": ("desk", "claims")}


def test_a_rule_nested_in_a_listed_grouping_selects_from_that_grouping_s_members() -> None:
    placement = _placed([
        {"label": "Front", "entity-ids": ["portal", "clerk", "desk"],
         "groups": [{"label": "Services", "rule": {"type": "business-service"}}]},
    ])

    assert _members(placement) == {"Front": ("portal", "clerk"), "Services": ("desk",)}
    assert "claims" in placement.unclaimed, "a rule inside a listed box does not reach outside it"


def test_a_listed_grouping_inside_a_ruled_one_keeps_what_it_lists() -> None:
    placement = _placed([
        {"label": "Business", "rule": {"domain": "business"},
         "groups": [{"label": "Guests", "entity-ids": ["host"]}]},
    ])

    assert _members(placement) == {"Business": ("clerk", "desk", "claims"), "Guests": ("host",)}


def test_only_a_stated_rule_makes_the_stated_groupings_the_whole_list() -> None:
    assert not states_a_ruled_grouping([{"label": "Front", "entity-ids": ["portal"]}])
    assert states_a_ruled_grouping([{"label": "Front", "groups": [{"label": "S", "rule": {"type": "node"}}]}])


def test_every_grouping_gets_an_id_of_its_own_and_keeps_the_one_it_has() -> None:
    stated = [
        {"label": "Front", "entity-ids": ["portal"], "groups": [{"label": "Inner", "entity-ids": ["clerk"]}]},
        {"id": "g-Kept01", "label": "Back"},
        {"label": "Front", "entity-ids": []},
    ]

    identified = with_grouping_ids(stated, diagram_id="ARC@1700000000.AbCdEf")
    again = with_grouping_ids(stated, diagram_id="ARC@1700000000.AbCdEf")

    ids = grouping_ids(identified)
    assert len(ids) == 4 and len(set(ids)) == 4
    assert "g-Kept01" in ids
    assert identified == again, "the same statement is given the same ids wherever it is identified"
    assert with_grouping_ids(identified, diagram_id="ARC@1700000000.AbCdEf") == identified
    assert list(identified[0])[0] == "id"
    assert check_groupings(identified) == []


def test_a_stored_grouping_without_an_id_is_refused_with_what_to_run() -> None:
    problems = check_groupings([{"label": "Front", "entity-ids": ["portal"]}])

    assert len(problems) == 1
    assert "arch-repair upgrade" in problems[0]


def test_what_a_grouping_may_not_say_is_named_in_a_sentence_each() -> None:
    problems = check_groupings([
        {"id": "g-aaaa", "label": "Both", "entity-ids": ["portal"], "rule": {"domain": "business"}},
        {"id": "g-aaaa", "label": "Twice"},
        {"id": "g-bbbb", "label": "Odd rule", "rule": {"colour": "red"}},
        {"id": "g-cccc", "label": "Two rules", "rule": {"domain": "a", "type": "b"}},
        {"id": "seven", "label": "Odd id"},
        {"id": "g-dddd", "label": "Extra", "colour": "red"},
        "not a grouping",
    ])

    said = " | ".join(problems)
    for expected in ("listed or ruled", "repeats the grouping id", "{domain: <name>}", "exactly one",
                     "a grouping id reads", "states colour", "expected a mapping"):
        assert expected in said, expected
    assert all(problem.rstrip().endswith(".") for problem in problems)
