"""Detector/migrator for shipped default attribute + frontmatter schemata.

Probes the exact `.arch-repo/schemata/` filenames the product ships defaults for:
a missing file is auto-added with the shipped payload; a present same-named file
is preserved byte-for-byte, and reported (info) only when it structurally differs
from the shipped default — an operator's local edit is never overwritten and never
silently drifts out of sight.
"""

from __future__ import annotations

import json

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_SCHEMATA_DIR = ".arch-repo/schemata"


class DefaultSchemataEnsureStep:
    id = "default-schemata-ensure"
    version = 1
    description = "Add missing shipped default schema files (never overwriting existing ones)"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for filename, payload in DEFAULT_SCHEMATA.items():
            location = f"{_SCHEMATA_DIR}/{filename}"
            content = view.read_text(location)
            if content is None:
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"missing-default-schema:{filename}",
                        location=location,
                        description=f"shipped default schema {filename} is absent",
                        severity="info",
                        auto_migratable=True,
                        rewrite_summary=f"add the shipped default {filename}",
                    )
                )
                continue
            if _differs_from_default(content, payload):
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"customized-default-schema:{filename}",
                        location=location,
                        description=(
                            f"{filename} differs from the shipped default — preserved as-is "
                            "(operator-owned customization)"
                        ),
                        severity="info",
                        auto_migratable=False,
                        manual_instructions=(
                            "No action required: your customized schema is never overwritten. "
                            "Delete the file and re-run to restore the shipped default."
                        ),
                    )
                )
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        results: list[AppliedFinding] = []
        for finding in findings:
            filename = finding.location.rsplit("/", 1)[-1]
            payload = DEFAULT_SCHEMATA.get(filename)
            if payload is None or view.read_text(finding.location) is not None:
                results.append(AppliedFinding(finding=finding, outcome="skipped", detail="already present"))
                continue
            writer.write_text(finding.location, json.dumps(payload, indent=2) + "\n")
            results.append(AppliedFinding(finding=finding, outcome="applied"))
        return results


def _differs_from_default(content: str, payload: dict) -> bool:
    try:
        return json.loads(content) != payload
    except json.JSONDecodeError:
        # Malformed JSON is schema-file-scan's finding, not a customization.
        return False
