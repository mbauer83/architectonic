"""Deciding whether a proposed change is already in the enterprise artifact.

Cycle 1 measured the two candidate mechanisms and this is the one that survived: compare the fields
the edit actually names against what the artifact says now. The rejected alternative — replay the
edit and diff the rendered result — fails on its own output, because a replay re-renders the whole
artifact and normalises quoting, key order and whitespace.

The asymmetry in the failure modes is the design: a change wrongly left open is one an author can
still submit; one wrongly closed is one that silently never happens. So every case below that cannot
be decided resolves to *not integrated*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.integration_detection import current_values_of, integration_verdict
from src.application.modeling.proposal_edit import ProposalEdit
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord

TARGET = "APP@1780000000.aaaaaaa.payments-service"


def _entity(*, name="Payments", status="draft", keywords=("pay",), summary="Handles payments.") -> EntityRecord:
    return EntityRecord(
        artifact_id=TARGET,
        artifact_type="application-component",
        name=name,
        version="0.1.0",
        status=status,
        domain="application",
        subdomain="application-component",
        path=Path("/repo/model/application/application-component/payments.md"),
        keywords=keywords,
        extra={},
        content_text=f"## {name}\n\n{summary}\n\n## Properties\n\n## Notes\n\n",
        display_blocks={},
        display_label=name,
        display_alias="payments",
    )


def _edit(**fields) -> ProposalEdit:
    return ProposalEdit(kind="entity", artifact_id=TARGET, fields=fields)


class TestAChangeTheReviewerApplied:
    def test_a_matching_field_reports_integrated(self) -> None:
        record = _entity(name="Payments Platform")

        verdict = integration_verdict(_edit(name="Payments Platform"), current_values_of(record))

        assert verdict.integrated
        assert verdict.matching == ("name",)

    def test_every_field_must_match_not_merely_one(self) -> None:
        """A partially applied change is not integrated: the rest still has to reach the reviewer."""
        record = _entity(name="Payments Platform", status="draft")

        verdict = integration_verdict(
            _edit(name="Payments Platform", status="accepted"), current_values_of(record)
        )

        assert not verdict.integrated
        assert verdict.matching == ("name",)
        assert verdict.differing == ("status",)

    def test_a_list_field_matches_across_the_two_readings(self) -> None:
        """One side arrives from YAML as a list, the other from the record as a tuple."""
        record = _entity(keywords=("pay", "ledger"))

        verdict = integration_verdict(_edit(keywords=["pay", "ledger"]), current_values_of(record))

        assert verdict.integrated

    def test_surrounding_whitespace_does_not_defeat_a_match(self) -> None:
        record = _entity(summary="Handles payments.")

        verdict = integration_verdict(_edit(summary="  Handles payments.  "), current_values_of(record))

        assert verdict.integrated

    def test_internal_whitespace_is_a_real_difference(self) -> None:
        """Collapsing it would close a change nobody applied."""
        record = _entity(summary="Handles payments.")

        verdict = integration_verdict(_edit(summary="Handles   payments."), current_values_of(record))

        assert not verdict.integrated
        assert verdict.differing == ("summary",)


class TestWhatIsNotDecidable:
    def test_a_target_that_cannot_be_read_is_undecidable_not_different(self) -> None:
        """An unmounted enterprise repository is missing evidence, not evidence of integration."""
        verdict = integration_verdict(_edit(name="Payments Platform"), None)

        assert not verdict.integrated
        assert verdict.undecidable == ("name",)
        assert verdict.differing == ()

    def test_a_field_with_no_current_reading_leaves_the_change_open(self) -> None:
        record = _entity()

        verdict = integration_verdict(_edit(attribute_types={"tier": "string"}), current_values_of(record))

        assert not verdict.integrated
        assert verdict.undecidable == ("attribute_types",)

    def test_a_diagram_proposal_is_never_closed_automatically(self) -> None:
        """Most of a diagram's editable fields are nested documents with no single current value."""
        assert current_values_of(None) is None

        verdict = integration_verdict(
            ProposalEdit(kind="diagram", artifact_id="ARC@1.a.b", fields={"name": "A View"}), None
        )

        assert not verdict.integrated
        assert verdict.undecidable == ("name",)

    def test_an_undecidable_field_beside_a_matching_one_still_blocks(self) -> None:
        """Otherwise a change closes on the half that could be read."""
        record = _entity(name="Payments Platform")

        verdict = integration_verdict(
            _edit(name="Payments Platform", attribute_types={"tier": "string"}), current_values_of(record)
        )

        assert not verdict.integrated
        assert verdict.matching == ("name",)
        assert verdict.undecidable == ("attribute_types",)


class TestDocuments:
    def _document(self, *, title="A Decision", status="draft") -> DocumentRecord:
        return DocumentRecord(
            artifact_id="ADR@1780000001.bbbbbbb.a-decision",
            doc_type="adr",
            title=title,
            status=status,
            path=Path("/repo/docs/adr/a-decision.md"),
            keywords=(),
            sections=(),
            content_text="",
            extra={},
        )

    def test_a_matching_title_reports_integrated(self) -> None:
        verdict = integration_verdict(
            ProposalEdit(kind="document", artifact_id="ADR@1780000001.bbbbbbb.a-decision",
                         fields={"title": "A Better Decision"}),
            current_values_of(self._document(title="A Better Decision")),
        )

        assert verdict.integrated

    def test_a_body_proposal_is_left_for_a_person(self) -> None:
        """The write path reformats prose, so comparing it would report an integration the moment a
        reviewer rewrapped a line."""
        verdict = integration_verdict(
            ProposalEdit(kind="document", artifact_id="ADR@1780000001.bbbbbbb.a-decision",
                         fields={"body": "New prose."}),
            current_values_of(self._document()),
        )

        assert not verdict.integrated
        assert verdict.undecidable == ("body",)


def test_a_change_that_proposes_what_is_already_true_reports_integrated() -> None:
    """Not a special case — it is the same comparison, and the answer is honest: nothing to submit."""
    record = _entity(name="Payments")

    verdict = integration_verdict(_edit(name="Payments"), current_values_of(record))

    assert verdict.integrated


@pytest.mark.parametrize("status", ["draft", "accepted", "superseded"])
def test_the_verdict_does_not_depend_on_the_artifact_s_own_status(status) -> None:
    """A reviewer may accept a change without promoting the artifact's lifecycle."""
    record = _entity(name="Payments Platform", status=status)

    assert integration_verdict(_edit(name="Payments Platform"), current_values_of(record)).integrated
