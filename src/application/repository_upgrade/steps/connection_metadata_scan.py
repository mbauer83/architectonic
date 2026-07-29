"""Read-only detector for the per-connection metadata block (D6): flags a fenced ```yaml
block under a `### ` connection heading that fails to parse as a mapping.

This is a genuinely silent gap, not just a proactive echo of an already-loud live check:
`parse_connection_declarations` deliberately reinterprets a malformed fence as ordinary body
prose (so a broken block never crashes a read), and the live verifier's
`check_connection_metadata_schema` call is itself gated on `decl.metadata` being truthy — so
today a malformed metadata block produces zero warning anywhere. `arch-repair upgrade` is the
first thing to actually surface it.

Always manual: the author's intended metadata can't be reconstructed from broken YAML.
"""

from __future__ import annotations

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.connection_declaration import find_malformed_metadata_sections
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_GLOB = "**/*.outgoing.md"


class ConnectionMetadataScanStep:
    id = "connection-metadata-scan"
    version = 1
    description = "Flag connection metadata blocks that fail to parse as a mapping"
    scanned_surface: ScannedSurface = "connection_declarations"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for rel in view.list_files(_GLOB):
            content = view.read_text(rel)
            if content is None:
                continue
            for header in find_malformed_metadata_sections(content):
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"malformed-connection-metadata:{rel}:{header}",
                        location=rel,
                        description=f"Connection '{header}' has a metadata block that fails to parse as a mapping",
                        severity="warning",
                        auto_migratable=False,
                        manual_instructions=(
                            f"{rel}, connection '{header}': the fenced metadata block under this heading "
                            "is malformed (bad YAML, or not a mapping) and is currently silently read as "
                            "plain description text instead of structured metadata — review and fix by hand."
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
