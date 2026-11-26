"""Type the columns of a stored stress-analysis type that name a candidate, as the shipped type now types them.

The shipped type declares `adaptations.candidate_architecture` and `survival.architecture` as `id` columns of
candidate architectures (`document_tables`): a cell is written as the id its candidate is stored under, and one
naming no stored candidate is refused (E164). A repository's document types are never overwritten
(`shipped_defaults`), so a repository written before keeps the two plain-text columns, whose cells take any text
and whose readers had to join on it. This step gives each of the two the shipped declaration — read from the
shipped type, never restated — where it is still in that earlier form: no `type`, or `string`. A column the
repository typed otherwise is its own adaptation and is left alone, as is every other key of the type.

Rows are not rewritten. A short id names the same candidate as its slugged form (`canonical_entity_key`); a cell
naming a candidate that is gone is what verification reports from now on. Applying it twice changes nothing.
"""

from __future__ import annotations

import json
from typing import Any

from src.application.artifacts.document_tables import stated_columns
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.repository.shipped_defaults import shipped_document_type

#: The columns that name a candidate, by table.
_CANDIDATE_COLUMNS = (("adaptations", "candidate_architecture"), ("survival", "architecture"))
#: How a column was declared before it was typed: with no type, or as text.
_PLAIN = (None, "string")
_FINDING = "stress-analysis-names-a-candidate-in-plain-text"


def _columns(declared: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Each column of *declared* that names a candidate, by its table and name, as the file states it."""
    return {
        (table, column["name"]): column for table, column in stated_columns(declared)
        if (table, column["name"]) in _CANDIDATE_COLUMNS
    }


def _retyped(stored: dict[str, Any]) -> dict[str, Any] | None:
    """*stored* with each plain column that names a candidate declared as the shipped type declares it; None
    where none is plain."""
    shipped = _columns(json.loads(shipped_document_type(STRESS_ANALYSIS).text))
    plain = {key for key, column in _columns(stored).items() if column.get("type") in _PLAIN}
    if not plain:
        return None
    retyped = json.loads(json.dumps(stored))
    for key, column in _columns(retyped).items():
        if key in plain:
            column.clear()
            column.update(shipped[key])
    return retyped


class StressAnalysisCandidateColumnsStep:
    id = "stress-analysis-candidate-columns"
    version = 1
    description = "Name the candidate an adaptation or a verdict is about by its id, refusing one that is not stored"
    scanned_surface: ScannedSurface = "profiles"

    @staticmethod
    def _location() -> str:
        return shipped_document_type(STRESS_ANALYSIS).location

    def _stored(self, view: RepoUpgradeView) -> dict[str, Any] | None:
        text = view.read_text(self._location())
        return json.loads(text) if text else None

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        stored = self._stored(view)
        if stored is None or _retyped(stored) is None:
            return []
        return [UpgradeFinding(
            step_id=self.id, finding_id=f"{_FINDING}:{self._location()}", location=self._location(),
            description="the stress-analysis type names an adaptation's and a verdict's candidate in plain text",
            severity="info", auto_migratable=True,
            rewrite_summary="declare both as ids of candidate architectures, as the shipped type does",
        )]

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        return [self._applied(view, writer, finding) for finding in findings]

    def _applied(self, view: RepoUpgradeView, writer: RepoUpgradeWriter, finding: UpgradeFinding) -> AppliedFinding:
        stored = self._stored(view)
        if stored is None:
            return AppliedFinding(finding=finding, outcome="error", detail="file no longer exists")
        retyped = _retyped(stored)
        if retyped is None:
            return AppliedFinding(finding=finding, outcome="skipped", detail="already current")
        writer.write_text(finding.location, json.dumps(retyped, indent=2) + "\n")
        return AppliedFinding(finding=finding, outcome="applied")
