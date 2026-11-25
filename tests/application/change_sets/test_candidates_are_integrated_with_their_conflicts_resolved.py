"""Integrating candidates (S4): a new draft holding every candidate's operations, each conflict settled by an
action it permits — take one side, drop one operation, or write a merged value — applied in order, each over
what the ones before left."""

from __future__ import annotations

import pytest

from src.application.change_sets.base import BaseRevision
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.integration import (
    Integration,
    Resolution,
    UnresolvableIntegration,
    integrate,
)
from src.application.change_sets.operations import AddConnection, Operation, RemoveEntity
from tests.support.change_sets import candidate, create, edit, joins

_A = "ENT@1.a"
_B = "ENT@1.b"
_NAIVE = "CAND@1.naive"


_REVISION = BaseRevision("0123456789abcdef")


def _on_naive(*operations: Operation, id: str, **header: object) -> CandidateArchitecture:  # noqa: A002
    return candidate(*operations, id=id, parent_id=_NAIVE, **header)


def _integrated(*candidates: CandidateArchitecture, resolutions: tuple[Resolution, ...] = ()) -> Integration:
    return integrate(
        candidates, resolutions, id="CAND@2.integration", name="Integration", rationale="", revision="rev-now",
    )


def _made(result: Integration) -> CandidateArchitecture:
    assert result.candidate is not None, result.conflicts
    return result.candidate


def _names(ours: str, theirs: str) -> tuple[CandidateArchitecture, CandidateArchitecture]:
    return (
        _on_naive(edit(_A, "name", ours, was="Billing"), id="CAND@1.ours", answers=("E1",)),
        _on_naive(edit(_A, "name", theirs, was="Billing"), id="CAND@1.theirs", answers=("E2",)),
    )


def test_candidates_that_do_not_conflict_are_integrated_at_once_on_their_parent() -> None:
    ours = _on_naive(edit(_A, "name", "Invoicing", was="Billing"), id="CAND@1.ours", answers=("E1",))
    theirs = _on_naive(edit(_B, "name", "Ledger", was="Books"), id="CAND@1.theirs", satisfies=("REQ@1.r",))

    result = _integrated(ours, theirs)

    assert result.conflicts == ()
    made = _made(result)
    assert (made.state, made.parent_id, made.changes.repository_revision) == ("draft", _NAIVE, "rev-now")
    assert {op.value for op in made.changes.operations} == {"Invoicing", "Ledger"}
    assert (made.answers, made.satisfies) == (("E1",), ("REQ@1.r",))


def test_converging_operations_are_held_once() -> None:
    result = _integrated(*_names("Invoicing", "Invoicing"))

    assert len(_made(result).changes.operations) == 1


def test_a_conflict_is_listed_with_its_actions_and_nothing_is_made() -> None:
    result = _integrated(*_names("Invoicing", "Payments"))

    assert result.candidate is None
    (conflict,) = result.conflicts
    assert conflict.overlap.kind == "same-key"
    assert [party.set_id for party in conflict.overlap.parties] == ["CAND@1.ours", "CAND@1.theirs"]
    assert conflict.actions == ("take", "drop", "merge")


@pytest.mark.parametrize(
    ("resolution", "name"),
    [
        (Resolution("same-key", "name of ENT@1.a", "take", party="CAND@1.theirs"), "Payments"),
        (Resolution("same-key", "name of ENT@1.a", "drop", party="CAND@1.theirs"), "Invoicing"),
        (Resolution("same-key", "name of ENT@1.a", "merge", value="Invoicing and Payments"), "Invoicing and Payments"),
    ],
)
def test_each_action_settles_a_same_key_conflict(resolution: Resolution, name: str) -> None:
    result = _integrated(*_names("Invoicing", "Payments"), resolutions=(resolution,))

    (operation,) = _made(result).changes.operations
    assert operation.value == name


def test_a_remove_against_a_use_is_settled_by_taking_a_side() -> None:
    removing = _on_naive(RemoveEntity(_B, base=_REVISION), id="CAND@1.removes")
    using = _on_naive(edit(_B, "name", "Ledger", was="Books"), id="CAND@1.uses")

    (conflict,) = _integrated(removing, using).conflicts
    assert (conflict.overlap.kind, conflict.actions) == ("remove-versus-use", ("take", "drop"))
    kept = _made(_integrated(removing, using, resolutions=(
        Resolution("remove-versus-use", conflict.overlap.subject, "take", party="CAND@1.removes"),
    )))

    assert [type(op).__name__ for op in kept.changes.operations] == ["RemoveEntity"]


def test_a_drop_among_three_leaves_the_two_that_still_disagree() -> None:
    three = (*_names("Invoicing", "Payments"),
             _on_naive(edit(_A, "name", "Billing Run", was="Billing"), id="CAND@1.third"))
    subject = "name of ENT@1.a"

    after_one = _integrated(*three, resolutions=(Resolution("same-key", subject, "drop", party="CAND@1.third"),))
    assert [p.set_id for p in after_one.conflicts[0].overlap.parties] == ["CAND@1.ours", "CAND@1.theirs"]

    settled = _integrated(*three, resolutions=(
        Resolution("same-key", subject, "drop", party="CAND@1.third"),
        Resolution("same-key", subject, "take", party="CAND@1.ours"),
    ))
    assert [op.value for op in _made(settled).changes.operations] == ["Invoicing"]


def test_a_resolution_naming_no_standing_conflict_is_refused() -> None:
    with pytest.raises(UnresolvableIntegration, match="No same-key conflict about name of ENT@1.b"):
        _integrated(*_names("Invoicing", "Payments"),
                    resolutions=(Resolution("same-key", "name of ENT@1.b", "take", party="CAND@1.ours"),))


def test_an_action_the_conflict_does_not_permit_is_refused() -> None:
    removing = _on_naive(RemoveEntity(_B, base=_REVISION), id="CAND@1.removes")
    using = _on_naive(edit(_B, "name", "Ledger", was="Books"), id="CAND@1.uses")
    (conflict,) = _integrated(removing, using).conflicts

    with pytest.raises(UnresolvableIntegration, match="permits take, drop, not merge"):
        _integrated(removing, using, resolutions=(
            Resolution("remove-versus-use", conflict.overlap.subject, "merge", value="x"),
        ))


def test_a_party_outside_the_conflict_is_refused() -> None:
    with pytest.raises(UnresolvableIntegration, match="name one of its parties"):
        _integrated(*_names("Invoicing", "Payments"),
                    resolutions=(Resolution("same-key", "name of ENT@1.a", "take", party="CAND@1.elsewhere"),))


def test_candidates_on_different_parents_or_final_ones_are_refused() -> None:
    ours, _theirs = _names("Invoicing", "Payments")
    loose = candidate(edit(_B, "name", "Ledger", was="Books"), id="CAND@1.loose")
    with pytest.raises(UnresolvableIntegration, match="different candidates"):
        _integrated(ours, loose)
    done = _on_naive(edit(_B, "name", "Ledger", was="Books"), id="CAND@1.done", state="integrated")
    with pytest.raises(UnresolvableIntegration, match="final"):
        _integrated(ours, done)
    with pytest.raises(UnresolvableIntegration, match="two or more"):
        _integrated(ours)


def test_two_candidates_creating_under_one_alias_are_refused_rather_than_merged() -> None:
    queue = "$ref:queue"
    creating = _on_naive(create(queue), AddConnection(joins(queue, _A), fields={}), id="CAND@1.creates")
    other = _on_naive(create(queue, name="Other queue"), id="CAND@1.other")

    with pytest.raises(ValueError, match="queue"):
        _integrated(creating, other)
