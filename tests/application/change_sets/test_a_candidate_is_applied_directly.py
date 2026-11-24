"""Applying a candidate directly: what is written, what is skipped, and the sentence that refuses it.

Judged against records: the standing is computed here exactly as the apply computes it, so each rule
is the application's decision over facts nothing recomputes.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.application.change_sets.candidate_apply import TERMINAL, judged
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.operations import AddConnection, CreateEntity
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.stacking import sets_beneath
from src.application.change_sets.standing import standing_of
from tests.support.change_sets import candidate, create, edit, joins

_A = "ENT@1.a"
_MODEL = RecordedReading(entities={_A: {"name": "Billing"}}, connections={})


def _judged(*stack: CandidateArchitecture):
    top = stack[-1]
    return judged(top, stack, standing_of(top.changes, _MODEL, beneath=sets_beneath(stack)))


def test_a_candidate_whose_operations_apply_is_not_refused_and_writes_them_all() -> None:
    rename = edit(_A, "name", "Invoicing", was="Billing")
    applied = _judged(candidate(rename))

    assert applied.refusal is None
    assert applied.applying.operations == (rename,)
    assert applied.integrated.state == "integrated"


def test_an_operation_already_there_is_skipped() -> None:
    already = edit(_A, "name", "Billing", was="Payments")
    rename_summary = edit(_A, "summary", "Takes payments.", was=None)
    applied = _judged(candidate(already, rename_summary))

    assert applied.refusal is None
    assert applied.applying.operations == (rename_summary,)


def test_a_create_already_there_stays_nameable_by_what_still_applies() -> None:
    present = CreateEntity(ref="billing", fields={"artifact_type": "application-component", "name": "Billing",
                                                  "group": "uncategorized"}, artifact_id=_A)
    link = AddConnection(joins(present.reference, "ENT@1.b"), {})
    model = RecordedReading(entities={_A: {"name": "Billing"}, "ENT@1.b": {"name": "Ledger"}}, connections={})
    top = candidate(present, link)

    applied = judged(top, (top,), standing_of(top.changes, model))

    assert applied.applying.operations == (link,)
    assert applied.named.operations == (present,)
    assert applied.ids == {"billing": _A}


def test_a_conflicting_operation_refuses_the_apply_in_its_own_words() -> None:
    gone = edit("ENT@1.gone", "name", "Ghost", was="Spectre")
    applied = _judged(candidate(gone))

    (standing,) = applied.standing
    assert standing.standing == "conflicting"
    assert applied.refusal is not None and standing.reason in applied.refusal


def test_a_drifted_operation_refuses_the_apply_until_it_is_re_based() -> None:
    drifted = edit(_A, "name", "Invoicing", was="Payments")
    applied = _judged(candidate(drifted))

    (standing,) = applied.standing
    assert standing.standing == "drifted"
    assert applied.refusal is not None
    assert "re-based" in applied.refusal and standing.reason in applied.refusal


def test_a_conflict_is_reported_before_drift() -> None:
    applied = _judged(candidate(
        edit("ENT@1.gone", "name", "Ghost", was="Spectre"), edit(_A, "name", "Invoicing", was="Payments"),
    ))

    assert applied.refusal is not None and "re-based" not in applied.refusal


@pytest.mark.parametrize("state", sorted(TERMINAL))
def test_a_terminal_candidate_is_not_applied_again(state: str) -> None:
    applied = _judged(candidate(edit(_A, "name", "Invoicing", was="Billing"), state=state))

    assert applied.refusal is not None and state in applied.refusal


def test_a_candidate_with_no_operations_has_nothing_to_apply() -> None:
    applied = _judged(candidate())

    assert applied.refusal is not None and "nothing to apply" in applied.refusal


def test_a_candidate_on_a_parent_not_yet_integrated_asks_for_the_parent_first() -> None:
    queue = replace(create("queue"), artifact_id="ENT@1.queue")
    lower = candidate(queue, id="CA-1")
    upper = candidate(edit(_A, "name", "Invoicing", was="Billing"), id="CA-2", parent_id="CA-1")

    applied = _judged(lower, upper)

    assert applied.refusal is not None and "CA-1" in applied.refusal and "first" in applied.refusal
    assert _judged(replace(lower, state="integrated"), upper).refusal is None


def test_what_a_parent_creates_is_named_by_the_id_chosen_for_it() -> None:
    queue = CreateEntity(ref="queue", fields={"artifact_type": "application-component", "name": "Queue",
                                              "group": "uncategorized"}, artifact_id="ENT@1.queue")
    lower = candidate(queue, id="CA-1", state="integrated")
    upper = candidate(AddConnection(joins(queue.reference, _A), {}), id="CA-2", parent_id="CA-1")

    applied = _judged(lower, upper)

    assert applied.named.operations == (queue,)
    assert applied.ids == {"queue": "ENT@1.queue"}
