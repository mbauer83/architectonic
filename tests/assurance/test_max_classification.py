"""Tests for TLP max-classification ceiling (SC-4).

Covers:
  - the TLP order: WHITE < GREEN < AMBER < RED
  - exceeds_ceiling: edge cases, and unknown values failing closed
  - AssuranceExposurePolicy.filter_security_records: correct keep/withheld split
  - Assurance node redaction via AssuranceContext.withheld_response
"""

from __future__ import annotations

import pytest

# ── TLP helpers ───────────────────────────────────────────────────────────────


class TestTLPHelpers:
    def test_ordering(self) -> None:
        from src.domain.assurance.classification import content_rank

        assert content_rank("TLP:WHITE") < content_rank("TLP:GREEN")
        assert content_rank("TLP:GREEN") < content_rank("TLP:AMBER")
        assert content_rank("TLP:AMBER") < content_rank("TLP:RED")

    @pytest.mark.parametrize("unrecognised", ["TLP:UNKNOWN", "red", "", None, "TLP: AMBER"])
    def test_unrecognised_content_is_withheld_below_red(self, unrecognised: str | None) -> None:
        """Regression: an unrecognised level ranked as TLP:WHITE and was shown under any ceiling."""
        from src.domain.assurance.classification import exceeds_ceiling

        assert exceeds_ceiling(unrecognised, "TLP:AMBER")
        assert not exceeds_ceiling(unrecognised, "TLP:RED")

    def test_an_unrecognised_ceiling_admits_only_white(self) -> None:
        from src.domain.assurance.classification import exceeds_ceiling

        assert not exceeds_ceiling("TLP:WHITE", "TLP:BOGUS")
        assert exceeds_ceiling("TLP:GREEN", "TLP:BOGUS")

    def test_is_above_ceiling_equal_not_above(self) -> None:
        from src.domain.assurance.classification import exceeds_ceiling

        assert not exceeds_ceiling("TLP:AMBER", "TLP:AMBER")

    def test_is_above_ceiling_below_not_above(self) -> None:
        from src.domain.assurance.classification import exceeds_ceiling

        assert not exceeds_ceiling("TLP:GREEN", "TLP:AMBER")
        assert not exceeds_ceiling("TLP:WHITE", "TLP:RED")

    def test_is_above_ceiling_above(self) -> None:
        from src.domain.assurance.classification import exceeds_ceiling

        assert exceeds_ceiling("TLP:RED", "TLP:AMBER")
        assert exceeds_ceiling("TLP:AMBER", "TLP:GREEN")
        assert exceeds_ceiling("TLP:RED", "TLP:WHITE")

    def test_case_and_whitespace_insensitive(self) -> None:
        from src.domain.assurance.classification import exceeds_ceiling

        assert not exceeds_ceiling(" tlp:amber ", "TLP:AMBER")

    def test_a_derived_figure_takes_its_most_sensitive_contributor(self) -> None:
        """Regression: an unrecognised contributor was dropped, understating the classification."""
        from src.domain.assurance.classification import most_sensitive

        assert most_sensitive(["TLP:WHITE", "TLP:AMBER"]) == "TLP:AMBER"
        assert most_sensitive(["TLP:WHITE", "bogus"]) == "TLP:RED"
        assert most_sensitive([]) is None


# ── Signal filter (via AssuranceExposurePolicy) ───────────────────────────────


class TestFilterByCeiling:
    def test_all_pass_when_below_ceiling(self) -> None:
        from src.application.assurance.exposure import AssuranceExposurePolicy

        pol = AssuranceExposurePolicy("TLP:AMBER", True)
        records = [
            {"tlp": "TLP:WHITE"},
            {"tlp": "TLP:GREEN"},
            {"tlp": "TLP:AMBER"},
        ]
        kept, withheld = pol.filter_security_records(records)
        assert kept == records
        assert withheld == 0

    def test_red_withheld_at_amber_ceiling(self) -> None:
        from src.application.assurance.exposure import AssuranceExposurePolicy

        pol = AssuranceExposurePolicy("TLP:AMBER", True)
        records = [
            {"id": 1, "tlp": "TLP:GREEN"},
            {"id": 2, "tlp": "TLP:RED"},
        ]
        kept, withheld = pol.filter_security_records(records)
        assert len(kept) == 1
        assert kept[0]["id"] == 1
        assert withheld == 1

    def test_all_withheld_at_white_ceiling(self) -> None:
        from src.application.assurance.exposure import AssuranceExposurePolicy

        pol = AssuranceExposurePolicy("TLP:WHITE", True)
        records = [
            {"tlp": "TLP:GREEN"},
            {"tlp": "TLP:AMBER"},
            {"tlp": "TLP:RED"},
        ]
        kept, withheld = pol.filter_security_records(records)
        assert kept == []
        assert withheld == 3

    def test_missing_tlp_treated_as_amber_passes_amber_ceiling(self) -> None:
        from src.application.assurance.exposure import AssuranceExposurePolicy

        pol = AssuranceExposurePolicy("TLP:AMBER", True)
        records = [{"id": 1}]  # no tlp field → defaults TLP:AMBER → passes ceiling
        kept, withheld = pol.filter_security_records(records)
        assert len(kept) == 1
        assert withheld == 0

    def test_empty_input(self) -> None:
        from src.application.assurance.exposure import AssuranceExposurePolicy

        pol = AssuranceExposurePolicy("TLP:AMBER", True)
        kept, withheld = pol.filter_security_records([])
        assert kept == []
        assert withheld == 0


# ── Context withheld_response ─────────────────────────────────────────────────


class TestWithheldResponse:
    def test_withheld_response_structure(self) -> None:
        from unittest.mock import patch

        from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

        ctx = AssuranceContext()
        with patch("src.config.storage_settings.storage_assurance_max_classification", return_value="TLP:AMBER"):
            resp = ctx.withheld_response("NODE@123", "TLP:RED")

        # The shared in-band shape: the code names the refusal, and the classification data a
        # caller acts on rides under `details` rather than spread across sibling keys.
        error = resp["error"]
        assert isinstance(error, dict)
        assert error["code"] == "classification_ceiling_exceeded"
        assert error["path"] == "node_id"
        assert error["details"] == {
            "node_id": "NODE@123",
            "tlp": "TLP:RED",
            "ceiling": "TLP:AMBER",
        }

    def test_withheld_response_includes_hint(self) -> None:
        from unittest.mock import patch

        from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

        ctx = AssuranceContext()
        with patch("src.config.storage_settings.storage_assurance_max_classification", return_value="TLP:GREEN"):
            resp = ctx.withheld_response("NODE@456", "TLP:AMBER")

        error = resp["error"]
        assert isinstance(error, dict)
        # The ceiling is named in the sentence, so a reader is told what to change, not just that
        # they were refused.
        assert "TLP:GREEN" in str(error["message"])


# ── SC-5: ArtifactStorePort return type smoke ─────────────────────────────────


class TestArtifactStorePortAnnotation:
    def test_shared_artifact_index_return_type_annotation(self) -> None:
        """shared_artifact_index return annotation should be ReadableArtifactStore (not ArtifactIndex)."""
        import typing

        from src.application.ports import ReadableArtifactStore
        from src.infrastructure.artifact_index import factory as factory_module

        # get_type_hints resolves PEP-563 string annotations to actual types
        hints = typing.get_type_hints(factory_module.shared_artifact_index)
        assert "return" in hints
        assert hints["return"] is ReadableArtifactStore
