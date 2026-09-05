"""A read of enterprise content shows the author's own change, not the baseline they cannot write.

Until this existed a read returned the enterprise values, with a badge naming which fields differed
and never what they now said. An author who changed a summary and reopened the artifact saw the old
one — so the next edit was written over work they could not see, and accepting both in order would
have silently undone the first.

**Only the view composes.** The recorded change keeps the enterprise revision it was written
against, because staleness is decided by comparing that revision against enterprise HEAD. A composed
*base* would name a state existing nowhere upstream, and the comparison would stop meaning anything.
The last test here is the one that says so.
"""

from __future__ import annotations

from src.application.modeling.proposal_composition import composed_fields, composed_view
from src.application.modeling.proposal_edit import ProposalEdit
from src.application.modeling.proposal_standing import PendingProposal

_BASELINE = {
    "artifact_id": "REQ@1.a.two-tier",
    "name": "Two-tier repositories",
    "summary": "The enterprise wording.",
    "keywords": ["tiering"],
    "notes": "",
}


def _change(proposal_id: str, *, state: str = "draft", **fields: object) -> PendingProposal:
    edit = ProposalEdit(kind="entity", artifact_id="REQ@1.a.two-tier", fields=fields)
    return PendingProposal(
        proposal_id=proposal_id,
        target_id="REQ@1.a.two-tier",
        changed_fields=tuple(sorted(fields)),
        base_revision="rev-1",
        state=state,
        edit=edit,
    )


def test_composing_does_not_care_which_lifecycle_state_a_change_is_in() -> None:
    """A submitted change is as much the author's own work as a draft, and reads the same."""
    submitted = _change("PC@1", state="submitted", summary="Under review.")
    assert composed_view(_BASELINE, [submitted])["summary"] == "Under review."


def test_a_changed_field_reads_as_the_authors_value() -> None:
    """The defect, stated. This returned the enterprise wording."""
    composed = composed_view(_BASELINE, [_change("PC@1", summary="What the author wrote.")])
    assert composed["summary"] == "What the author wrote."


def test_an_untouched_field_still_reads_as_the_baseline() -> None:
    composed = composed_view(_BASELINE, [_change("PC@1", summary="What the author wrote.")])
    assert composed["name"] == "Two-tier repositories"


def test_a_field_the_baseline_does_not_carry_is_still_shown() -> None:
    """A payload omitting a field it has no value for is the ordinary case, not a reason to drop the
    author's."""
    composed = composed_view({"artifact_id": "REQ@1.a.two-tier"}, [_change("PC@1", notes="Added.")])
    assert composed["notes"] == "Added."


def test_nothing_pending_leaves_the_baseline_untouched() -> None:
    assert composed_view(_BASELINE, []) == _BASELINE


def test_the_baseline_passed_in_is_not_mutated() -> None:
    """Callers pass their own response payload; composing must not edit it under them."""
    baseline = dict(_BASELINE)
    composed_view(baseline, [_change("PC@1", summary="Changed.")])
    assert baseline == _BASELINE
    assert composed_view(baseline, [_change("PC@1", summary="Changed.")])["summary"] == "Changed."


def test_several_changes_fold_in_a_stable_order() -> None:
    """One change per artifact is what the product enforces; the stored shape still permits several,
    and a read that depended on gathering order would be wrong in a way nothing would report."""
    later = _change("PC@2", summary="Second.")
    earlier = _change("PC@1", summary="First.")
    assert composed_view(_BASELINE, [later, earlier])["summary"] == "Second."
    assert composed_view(_BASELINE, [earlier, later])["summary"] == "Second."


def test_disjoint_changes_both_apply() -> None:
    composed = composed_view(_BASELINE, [_change("PC@1", summary="Mine."), _change("PC@2", notes="Also mine.")])
    assert composed["summary"] == "Mine."
    assert composed["notes"] == "Also mine."


# ── which fields are the author's ────────────────────────────────────────────


def test_the_composed_fields_are_the_ones_the_change_names() -> None:
    assert composed_fields([_change("PC@1", summary="x", notes="y")]) == ("notes", "summary")


def test_composed_fields_unions_across_changes_and_sorts() -> None:
    fields = composed_fields([_change("PC@2", notes="y"), _change("PC@1", summary="x")])
    assert fields == ("notes", "summary")


def test_nothing_pending_names_no_composed_fields() -> None:
    assert composed_fields([]) == ()


# ── the separation the rebase depends on ─────────────────────────────────────


def test_composing_does_not_touch_the_recorded_base_revision() -> None:
    """Staleness compares the recorded base against enterprise HEAD. A composed base would name a
    state existing nowhere upstream, and the comparison would decide nothing."""
    change = _change("PC@1", summary="Mine.")
    composed_view(_BASELINE, [change])
    assert change.base_revision == "rev-1"
    assert change.edit.fields == {"summary": "Mine."}
