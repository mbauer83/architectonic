"""Detector/migrator for shipped default attribute + frontmatter schemata.

Probes the exact `.arch-repo/schemata/` filenames the product ships defaults for:
a missing file is auto-added with the shipped payload; a present same-named file
is preserved byte-for-byte, and reported (info) only when it structurally differs
from the shipped default — an operator's local edit is never overwritten and never
silently drifts out of sight.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._shipped_files import (
    apply_missing_shipped,
    missing_shipped_findings,
)
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.repository.shipped_defaults import shipped_schemata


class DefaultSchemataEnsureStep:
    id = "default-schemata-ensure"
    version = 1
    description = "Add missing shipped default schema files (never overwriting existing ones)"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        shipped = shipped_schemata()
        missing = missing_shipped_findings(
            self.id, shipped, view, finding_prefix="missing-default-schema", what="the shipped default schema",
        )
        return missing + [
            self._customized(one.key, one.location)
            for one in shipped
            if (content := view.read_text(one.location)) is not None and _differs_from_default(content, one.payload)
        ]

    def _customized(self, filename: str, location: str) -> UpgradeFinding:
        return UpgradeFinding(
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

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        return apply_missing_shipped(shipped_schemata(), view, writer, findings)


def _differs_from_default(content: str, payload: Mapping[str, object]) -> bool:
    try:
        return json.loads(content) != payload
    except json.JSONDecodeError:
        # Malformed JSON is schema-file-scan's finding, not a customization.
        return False
