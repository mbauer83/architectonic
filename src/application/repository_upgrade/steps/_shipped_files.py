"""The upgrade's side of "write each shipped file that is missing, never overwrite".

What is shipped, where it goes and how it is written belong to `shipped_defaults`, which the
workspace template asks too. This is only the upgrade's vocabulary for it: a finding per missing
file, and applying a finding by writing that file — unless it has appeared since it was detected.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding
from src.domain.repository.shipped_defaults import ShippedFile, missing_shipped


def missing_shipped_findings(
    step_id: str, shipped: Iterable[ShippedFile], view: RepoUpgradeView, *, finding_prefix: str, what: str,
) -> list[UpgradeFinding]:
    """One auto-migratable finding for each file of *shipped* the repository lacks.

    *what* names the kind of file in a sentence: "the shipped document type".
    """
    return [
        UpgradeFinding(
            step_id=step_id,
            finding_id=f"{finding_prefix}:{one.key}",
            location=one.location,
            description=f"{what} {one.key} is absent",
            severity="info",
            auto_migratable=True,
            rewrite_summary=f"add {what} {one.key}",
        )
        for one in missing_shipped(shipped, lambda location: view.read_text(location) is not None)
    ]


def apply_missing_shipped(
    shipped: Iterable[ShippedFile],
    view: RepoUpgradeView,
    writer: RepoUpgradeWriter,
    findings: list[UpgradeFinding],
) -> list[AppliedFinding]:
    """Write the shipped file each finding names, skipping one the repository holds by now."""
    by_location = {one.location: one for one in shipped}
    results: list[AppliedFinding] = []
    for finding in findings:
        one = by_location.get(finding.location)
        if one is None or view.read_text(finding.location) is not None:
            results.append(AppliedFinding(finding=finding, outcome="skipped", detail="already present"))
            continue
        writer.write_text(finding.location, one.text)
        results.append(AppliedFinding(finding=finding, outcome="applied"))
    return results
