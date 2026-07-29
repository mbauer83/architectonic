"""Severity selection: maximum valid applicable score wins with provenance
retained; invalid vectors count as unknown (never crash, never 0.0); bands
follow the CVSS qualitative scale."""

from __future__ import annotations

from src.application.security_signals.severity import score_to_band, select_severity

V31_MEDIUM = "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N"          # 5.4
V30_CRITICAL = "CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"       # 10.0
V40_CRITICAL = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"  # 9.3


class TestSelection:
    def test_maximum_valid_score_wins_with_provenance(self) -> None:
        result = select_severity([
            {"type": "CVSS_V3", "score": V31_MEDIUM},
            {"type": "CVSS_V3", "score": V30_CRITICAL},
            {"type": "CVSS_V4", "score": V40_CRITICAL},
        ])
        assert result.selected is not None
        assert result.selected.cvss_score == 10.0
        assert result.selected.cvss_vector == V30_CRITICAL
        assert result.selected.nomenclature == "CVSS_V3"
        assert result.selected.severity_band == "critical"
        assert result.candidate_count == 3
        assert result.invalid_vector_count == 0

    def test_invalid_vectors_count_as_unknown_never_zero(self) -> None:
        result = select_severity([
            {"type": "CVSS_V3", "score": "CVSS:3.1/GARBAGE"},
            {"type": "CVSS_V3", "score": V31_MEDIUM},
        ])
        assert result.invalid_vector_count == 1
        assert result.selected is not None
        assert result.selected.cvss_score == 5.4

    def test_all_invalid_means_no_selection(self) -> None:
        result = select_severity([{"type": "CVSS_V3", "score": "nope"}])
        assert result.selected is None
        assert result.invalid_vector_count == 1

    def test_empty_entries_are_no_candidates(self) -> None:
        result = select_severity([])
        assert result.selected is None
        assert result.candidate_count == 0


class TestBands:
    def test_qualitative_scale(self) -> None:
        assert score_to_band(9.8) == "critical"
        assert score_to_band(7.0) == "high"
        assert score_to_band(5.4) == "medium"
        assert score_to_band(1.2) == "low"
        assert score_to_band(0.0) == "none"
