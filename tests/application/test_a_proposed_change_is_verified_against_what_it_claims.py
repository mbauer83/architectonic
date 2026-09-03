"""A proposed change is refused when it claims something the repository does not support.

Cycle 2's red-first: a change naming a global artifact reference that does not exist is refused, and
every field it must carry is checked independently — an author with three things wrong should be
told three things.

**What is deliberately not verified here is staleness.** Whether the enterprise artifact has moved
past the recorded base revision is answered against a repository at the moment someone asks; a
verifier reading a file cannot ask it, and storing the answer would produce a file that claims to
know something it does not. What the verifier does is make the question *answerable*: the base
revision must be recorded, because without it nothing later can decide whether the artifact moved.
The computation belongs with the read path that shows it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.proposal_edit import ProposalEdit, to_mapping
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
    STATES,
)
from src.application.verification._verifier_rules_internal_types import check_internal_entity
from src.application.verification._verifier_rules_proposed_change import check_proposed_change
from src.application.verification.artifact_verifier_types import Severity, VerificationResult

_GAR = "GAR@1786120500.Ref0001.a-promoted-capability"


class _Index:
    """The little a rule asks of a registry: which ids resolve, and what the enterprise tier holds.

    The proposed-change rule needs only the first. The global-artifact-reference rule needs the
    second, and the dispatch test below runs both — which is the point of it.
    """

    def __init__(self, *known: str, enterprise: tuple[str, ...] = ()) -> None:
        self._known = set(known)
        self._enterprise = set(enterprise)

    def find_file_by_id(self, artifact_id: str) -> Path | None:
        return Path(f"/model/{artifact_id}.md") if artifact_id in self._known else None

    def enterprise_entity_ids(self) -> set[str]:
        return set(self._enterprise)


def _frontmatter(**overrides: object) -> dict:
    recorded = to_mapping(
        ProposalEdit(kind="entity", artifact_id="CAP@1.aaaaaa.x", fields={"summary": "clearer"})
    )
    return {
        "artifact-type": PROPOSED_CHANGE_TYPE,
        PROPOSES_CHANGE_TO: _GAR,
        RECORDED_EDIT: recorded,
        BASE_REVISION: "9f2c1d4",
        PROPOSAL_STATE: "draft",
    } | overrides


def _check(fm: dict, *, known: tuple[str, ...] = (_GAR,)) -> VerificationResult:
    result = VerificationResult(path=Path("/model/PCH@1.aaaaaa.x.md"), file_type="entity")
    check_proposed_change(fm, _Index(*known), result, "loc")  # type: ignore[arg-type]
    return result


def _codes(result: VerificationResult) -> list[str]:
    return sorted(issue.code for issue in result.issues)


def test_a_well_formed_change_is_accepted() -> None:
    """The precondition: if the valid case failed, every refusal below would prove nothing."""
    assert _codes(_check(_frontmatter())) == []


class TestWhatItIsAbout:
    def test_a_change_naming_a_reference_that_does_not_exist_is_refused(self) -> None:
        result = _check(_frontmatter(), known=())
        assert _codes(result) == ["E146"]
        assert _GAR in result.issues[0].message

    def test_a_change_naming_no_reference_is_refused(self) -> None:
        assert "E145" in _codes(_check(_frontmatter(**{PROPOSES_CHANGE_TO: ""})))

    def test_an_unloaded_index_is_a_warning_and_not_a_refusal(self) -> None:
        """Absence of evidence is not evidence: an index that is not loaded proves nothing."""
        result = VerificationResult(path=Path("/x.md"), file_type="entity")
        check_proposed_change(_frontmatter(), None, result, "loc")
        assert _codes(result) == ["W145"]
        assert result.valid


class TestTheRecordedEdit:
    def test_a_change_recording_no_edit_is_refused(self) -> None:
        assert "E147" in _codes(_check(_frontmatter(**{RECORDED_EDIT: None})))

    def test_an_edit_that_is_not_a_mapping_is_refused(self) -> None:
        assert "E147" in _codes(_check(_frontmatter(**{RECORDED_EDIT: ["summary"]})))

    def test_an_edit_naming_an_uneditable_field_is_refused_in_the_union_s_words(self) -> None:
        """The union already answers which fields are editable; restating it would be a second answer."""
        broken = {"kind": "entity", "artifact-id": "CAP@1.aaaaaa.x", "fields": {"invented": 1}}
        result = _check(_frontmatter(**{RECORDED_EDIT: broken}))
        assert _codes(result) == ["E147"]
        assert "not editable" in result.issues[0].message

    def test_an_edit_against_a_kind_with_no_reference_is_refused(self) -> None:
        """A connection has no global artifact reference, so it cannot be proposed against."""
        broken = {"kind": "connection", "artifact-id": "x", "fields": {"description": "y"}}
        assert _codes(_check(_frontmatter(**{RECORDED_EDIT: broken}))) == ["E147"]


class TestWhatMakesStalenessAnswerable:
    def test_a_change_recording_no_base_revision_is_refused(self) -> None:
        result = _check(_frontmatter(**{BASE_REVISION: ""}))
        assert _codes(result) == ["E148"]
        assert "moved" in result.issues[0].message


class TestTheLifecycle:
    @pytest.mark.parametrize("state", STATES)
    def test_every_declared_state_is_accepted(self, state: str) -> None:
        assert _codes(_check(_frontmatter(**{PROPOSAL_STATE: state}))) == []

    @pytest.mark.parametrize("state", ["rejected", "prepared", "pushed", "", None])
    def test_anything_else_is_refused(self, state: object) -> None:
        """`rejected` among them: nothing can enter it, and a state nothing enters is not a state.

        `prepared` and `pushed` are a submission attempt's phases, not a proposal's — a proposal is
        never in a saga phase.
        """
        assert "E149" in _codes(_check(_frontmatter(**{PROPOSAL_STATE: state})))


class TestEachFieldIsCheckedIndependently:
    def test_three_faults_are_reported_as_three(self) -> None:
        """Stopping at the first would make the second round of corrections a surprise."""
        result = _check(
            _frontmatter(**{PROPOSES_CHANGE_TO: "", BASE_REVISION: "", PROPOSAL_STATE: "rejected"})
        )
        assert _codes(result) == ["E145", "E148", "E149"]
        assert all(issue.severity == Severity.ERROR for issue in result.issues)


class TestTheDispatchSendsEachInternalTypeToItsOwnRule:
    """Sharing the `internal` class does not mean sharing a shape."""

    def test_a_proposed_change_is_not_checked_as_a_reference(self) -> None:
        result = VerificationResult(path=Path("/x.md"), file_type="entity")
        check_internal_entity(_frontmatter(), _Index(_GAR), result, "loc")  # type: ignore[arg-type]
        assert _codes(result) == [], "the global-artifact-reference rule ran over a proposed change"

    def test_a_reference_is_still_checked_as_one(self) -> None:
        reference = {
            "artifact-type": "global-artifact-reference",
            "global-artifact-id": "CAP@1.aaaaaa.x",
            "global-artifact-type": "entity",
        }
        result = VerificationResult(path=Path("/x.md"), file_type="entity")
        index = _Index("CAP@1.aaaaaa.x", enterprise=("CAP@1.aaaaaa.x",))
        check_internal_entity(reference, index, result, "loc")  # type: ignore[arg-type]
        assert "E145" not in _codes(result), "the proposed-change rule ran over a reference"

    def test_an_internal_type_with_no_rule_is_left_to_the_shared_ones(self) -> None:
        result = VerificationResult(path=Path("/x.md"), file_type="entity")
        check_internal_entity({"artifact-type": "something-else"}, None, result, "loc")
        assert _codes(result) == []
