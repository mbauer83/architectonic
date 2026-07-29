"""Read-only detector for diagram/matrix `viewpoint:` frontmatter (D8): flags a value that
fails to parse. `parse_viewpoint_application` already raises loudly for a malformed shape
(missing `slug`, non-integer version, unknown `enforcement_override`) — but the live
verifier's `check_viewpoint_application` calls it unguarded, so today that raise crashes the
verify pass for the whole file rather than producing a clean report entry. `arch-repair
upgrade` turns the same signal into a proactive, non-crashing finding.

Always manual: the malformed value has no unambiguous auto-rewrite.
"""

from __future__ import annotations

from src.application.artifact_parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.viewpoints.viewpoint_application_parsing import parse_viewpoint_application


class ViewpointApplicationScanStep:
    id = "viewpoint-application-scan"
    version = 1
    description = "Flag diagram/matrix 'viewpoint:' frontmatter that fails to parse"
    scanned_surface: ScannedSurface = "diagram_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for rel in list_frontmatter_candidate_files(view):
            content = view.read_text(rel)
            if content is None or not content.startswith("---"):
                continue
            frontmatter = extract_yaml_block(content)
            if not isinstance(frontmatter, dict):
                continue
            if str(frontmatter.get("artifact-type", "")) != "diagram":
                continue
            raw = frontmatter.get("viewpoint")
            if raw is None:
                continue
            try:
                parse_viewpoint_application(raw, target_kind="diagram", target_id=rel)
            except ValueError as exc:
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"malformed-viewpoint-application:{rel}",
                        location=rel,
                        description=f"'viewpoint:' frontmatter fails to parse: {exc}",
                        severity="warning",
                        auto_migratable=False,
                        manual_instructions=(
                            f"{rel}: the 'viewpoint:' frontmatter value is malformed ({exc}) — this "
                            "currently raises when the live verifier/GUI loads this file. Review and "
                            "fix by hand."
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
