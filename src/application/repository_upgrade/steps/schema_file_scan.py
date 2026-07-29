"""Read-only detector for `.arch-repo/schemata/*.schema.json` (D13 profiles): flags a schema
file that is not valid JSON. Covers all three naming conventions
`artifact_schema.py` documents — `frontmatter.*`, `attributes.{type}[.{slug}]`, and
`connection-metadata.*` — since they share one failure mode (malformed JSON) and one
directory. A base-type attribute schema (`attributes.{type}.schema.json`) IS today's
persisted form of a "profile" (D13): there is no longer a separate `.arch-repo/profiles.yaml`
(see the profile/specialization design correction), so this is the profiles surface's
current on-disk shape.

Deliberately narrow: orphaned specialization-attachment schemata (a *valid* JSON file whose
slug matches no declared specialization) are already caught live by the W044 verifier rule
against the fully merged catalog — duplicating that here would need widening
`RepoUpgradeView` for a check that never silently passes today. This step only covers what
that live check can't: a schema file so malformed it would raise before any rule gets to run.
"""

from __future__ import annotations

import json

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_GLOB = ".arch-repo/schemata/*.schema.json"


class SchemaFileScanStep:
    id = "schema-file-scan"
    version = 1
    description = f"Flag {_GLOB} files that are not valid JSON"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for rel in view.list_files(_GLOB):
            content = view.read_text(rel)
            if content is None:
                continue
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"malformed-schema-json:{rel}",
                        location=rel,
                        description=f"{rel} is not valid JSON: {exc}",
                        severity="warning",
                        auto_migratable=False,
                        manual_instructions=(
                            f"{rel} failed to parse as JSON ({exc}). This schema is silently skipped "
                            "(free-schema fallback) until repaired — review and fix by hand."
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
        return []  # unreachable: every finding this step produces is auto_migratable=False
