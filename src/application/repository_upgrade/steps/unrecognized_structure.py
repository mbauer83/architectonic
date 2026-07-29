"""Catch-all anomaly detector: flags file structure this software recognizes
neither as current nor as any registered legacy pattern, so an old/drifted repo's upgrade
report is honestly incomplete-looking rather than falsely clean.

Deliberately narrow (avoid false-positive noise on ordinary content this step simply
doesn't have an opinion about): only frontmatter-bearing markdown files (content starting
with ``---``) are considered, and only three signals are checked — malformed/unparseable
frontmatter, a missing ``artifact-type``, or an ``artifact-type`` value that isn't a known
literal or a currently-registered entity type. Connection-record files (``source-entity``
present, no ``artifact-type`` by design) are excluded. Always manual — this step never
attempts a rewrite, it only raises attention.
"""

from __future__ import annotations

from src.application.artifact_parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_KNOWN_LITERAL_ARTIFACT_TYPES = frozenset({"diagram", "document"})


class UnrecognizedStructureScanStep:
    id = "unrecognized-structure-scan"
    version = 1
    description = "Flag frontmatter that matches no currently-recognized or known-legacy shape"
    scanned_surface: ScannedSurface = "entity_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        known_types = _KNOWN_LITERAL_ARTIFACT_TYPES | view.known_entity_type_names
        findings: list[UpgradeFinding] = []
        for rel in list_frontmatter_candidate_files(view):
            content = view.read_text(rel)
            if content is None or not content.startswith("---"):
                continue

            frontmatter = extract_yaml_block(content)
            if frontmatter is None:
                findings.append(
                    self._finding(
                        rel,
                        "malformed-frontmatter",
                        "starts with '---' but the frontmatter block is malformed or unterminated",
                    )
                )
                continue
            if not isinstance(frontmatter, dict):
                findings.append(
                    self._finding(rel, "frontmatter-not-a-mapping", "frontmatter block is not a YAML mapping")
                )
                continue
            if "source-entity" in frontmatter:
                continue  # connection record — artifact-type doesn't apply here

            artifact_type = frontmatter.get("artifact-type")
            if artifact_type is None:
                findings.append(self._finding(rel, "missing-artifact-type", "frontmatter has no 'artifact-type'"))
            elif str(artifact_type) not in known_types:
                findings.append(
                    self._finding(
                        rel,
                        "unrecognized-artifact-type",
                        f"'artifact-type: {artifact_type}' is not a diagram/document literal or a "
                        "currently-registered entity type",
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

    def _finding(self, location: str, reason: str, detail: str) -> UpgradeFinding:
        return UpgradeFinding(
            step_id=self.id,
            finding_id=f"{reason}:{location}",
            location=location,
            description=f"Unrecognized structure ({detail})",
            severity="warning",
            auto_migratable=False,
            manual_instructions=(
                f"{location}: {detail}. This doesn't match a shape any registered upgrade step or "
                "the current schema recognizes — review manually; it may need a dedicated upgrade "
                "step, or hand-repair via the normal MCP write tools."
            ),
        )
