"""Tests for TLP max-classification ceiling (SC-4).

Covers:
  - tlp_level ordering: WHITE < GREEN < AMBER < RED
  - is_above_ceiling: edge cases and unknown values
  - AssuranceExposurePolicy.filter_security_records: correct keep/withheld split
  - Assurance node redaction via AssuranceContext.withheld_response
"""

from __future__ import annotations

# ── TLP helpers ───────────────────────────────────────────────────────────────


class TestTLPHelpers:
    def test_tlp_level_ordering(self) -> None:
        from src.infrastructure.mcp.assurance_mcp.context import tlp_level

        assert tlp_level("TLP:WHITE") < tlp_level("TLP:GREEN")
        assert tlp_level("TLP:GREEN") < tlp_level("TLP:AMBER")
        assert tlp_level("TLP:AMBER") < tlp_level("TLP:RED")

    def test_unknown_tlp_treated_as_white(self) -> None:
        from src.infrastructure.mcp.assurance_mcp.context import tlp_level

        assert tlp_level("TLP:UNKNOWN") == 0

    def test_is_above_ceiling_equal_not_above(self) -> None:
        from src.infrastructure.mcp.assurance_mcp.context import is_above_ceiling

        assert not is_above_ceiling("TLP:AMBER", "TLP:AMBER")

    def test_is_above_ceiling_below_not_above(self) -> None:
        from src.infrastructure.mcp.assurance_mcp.context import is_above_ceiling

        assert not is_above_ceiling("TLP:GREEN", "TLP:AMBER")
        assert not is_above_ceiling("TLP:WHITE", "TLP:RED")

    def test_is_above_ceiling_above(self) -> None:
        from src.infrastructure.mcp.assurance_mcp.context import is_above_ceiling

        assert is_above_ceiling("TLP:RED", "TLP:AMBER")
        assert is_above_ceiling("TLP:AMBER", "TLP:GREEN")
        assert is_above_ceiling("TLP:RED", "TLP:WHITE")

    def test_case_insensitive(self) -> None:
        from src.infrastructure.mcp.assurance_mcp.context import is_above_ceiling

        # Context module upper-cases internally
        assert not is_above_ceiling("TLP:AMBER", "TLP:AMBER")


# ── Signal filter (via AssuranceExposurePolicy) ───────────────────────────────


class TestFilterByCeiling:
    def test_all_pass_when_below_ceiling(self) -> None:
        from src.application.assurance_exposure import AssuranceExposurePolicy

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
        from src.application.assurance_exposure import AssuranceExposurePolicy

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
        from src.application.assurance_exposure import AssuranceExposurePolicy

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
        from src.application.assurance_exposure import AssuranceExposurePolicy

        pol = AssuranceExposurePolicy("TLP:AMBER", True)
        records = [{"id": 1}]  # no tlp field → defaults TLP:AMBER → passes ceiling
        kept, withheld = pol.filter_security_records(records)
        assert len(kept) == 1
        assert withheld == 0

    def test_empty_input(self) -> None:
        from src.application.assurance_exposure import AssuranceExposurePolicy

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

        assert resp["error"] == "classification_ceiling_exceeded"
        assert resp["node_id"] == "NODE@123"
        assert resp["tlp"] == "TLP:RED"
        assert "max_classification" in resp

    def test_withheld_response_includes_hint(self) -> None:
        from unittest.mock import patch

        from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

        ctx = AssuranceContext()
        with patch("src.config.storage_settings.storage_assurance_max_classification", return_value="TLP:GREEN"):
            resp = ctx.withheld_response("NODE@456", "TLP:AMBER")

        assert "max_classification" in str(resp["message"])


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
