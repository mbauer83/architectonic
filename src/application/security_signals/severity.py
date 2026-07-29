"""Severity selection from upstream vulnerability records (§6.0(g)).

Multiple severities per vulnerability: select the MAXIMUM valid applicable
score, preserving the vector, nomenclature (CVSS_V2/V3/V4), and selection
provenance. Scores are computed locally from upstream-reported vectors via the
vetted `cvss` library — never synthesized from a band. Invalid vectors count
as unknown severity; they never crash the ingest and never score 0.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from cvss import CVSS2, CVSS3, CVSS4
from cvss.exceptions import CVSSError

_BAND_BOUNDS = (
    (9.0, "critical"),
    (7.0, "high"),
    (4.0, "medium"),
    (0.1, "low"),
)


def score_to_band(score: float) -> str:
    for bound, band in _BAND_BOUNDS:
        if score >= bound:
            return band
    return "none"


@dataclass(frozen=True)
class SelectedSeverity:
    cvss_score: float
    cvss_vector: str
    nomenclature: str  # e.g. CVSS_V3
    severity_band: str


@dataclass(frozen=True)
class SeveritySelection:
    selected: SelectedSeverity | None
    invalid_vector_count: int
    candidate_count: int


def _score_vector(nomenclature: str, vector: str) -> float | None:
    try:
        upper = nomenclature.upper()
        raw: object | None = None
        if upper == "CVSS_V2":
            raw = CVSS2(vector).scores()[0]
        elif upper in ("CVSS_V3", "CVSS_V3.1"):
            raw = CVSS3(vector).scores()[0]
        elif upper == "CVSS_V4":
            raw = CVSS4(vector).base_score
    except (CVSSError, ValueError, IndexError):
        return None
    return float(raw) if isinstance(raw, (int, float)) else None


def select_severity(severity_entries: Sequence[Mapping[str, Any]]) -> SeveritySelection:
    """OSV `severity` entries: [{"type": "CVSS_V3", "score": "<vector>"}, …]."""
    best: SelectedSeverity | None = None
    invalid = 0
    candidates = 0
    for entry in severity_entries:
        nomenclature = str(entry.get("type", ""))
        vector = str(entry.get("score", ""))
        if not nomenclature or not vector:
            continue
        candidates += 1
        score = _score_vector(nomenclature, vector)
        if score is None:
            invalid += 1
            continue
        if best is None or score > best.cvss_score:
            best = SelectedSeverity(
                cvss_score=score,
                cvss_vector=vector,
                nomenclature=nomenclature.upper(),
                severity_band=score_to_band(score),
            )
    return SeveritySelection(selected=best, invalid_vector_count=invalid, candidate_count=candidates)
