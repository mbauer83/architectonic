"""Multiplicity rename: the first real, auto-migratable repository-upgrade step.

Renames the legacy `include_cardinality` diagram-frontmatter annotation key (per
`diagram_connections[]` entry, YAML frontmatter key `connections`) to `include_multiplicity`
— the sole content/metadata ↔ code compatibility mechanism for the multiplicity rename (no
runtime dual-key acceptance exists in application code; see the PLAN's locked decisions and
the multiplicity-rename work's progress notes).

`apply()` deliberately does **not** reparse-and-redump the frontmatter (the way the live
write pipeline's `format_diagram_puml` does for validated writes): it replaces only the
exact `include_cardinality` mapping-key token, scoped to the frontmatter span, leaving
everything else in the file — including any uncommitted edit or field this step has no
opinion about — byte-for-byte untouched. That's what the step-conformance obligation
demands, and it's a stronger guarantee than a parse/redump round-trip would give
(no risk of reordering, quote-style changes, or comment loss).
"""

from __future__ import annotations

import re

from src.application.artifacts.parsing import extract_yaml_block
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_scan import list_frontmatter_candidate_files
from src.domain.repository.frontmatter import (
    Frontmatter,
    opens_with_frontmatter,
    read_frontmatter,
    replace_frontmatter_text,
)
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_LEGACY_KEY = "include_cardinality"
_CURRENT_KEY = "include_multiplicity"
_CONNECTIONS_KEY = "connections"

_LEGACY_KEY_TOKEN_RE = re.compile(rf"(?<![\w-]){_LEGACY_KEY}(?=\s*:)")


def _legacy_key_count(frontmatter: dict) -> int:
    connections = frontmatter.get(_CONNECTIONS_KEY)
    if not isinstance(connections, list):
        return 0
    return sum(1 for entry in connections if isinstance(entry, dict) and _LEGACY_KEY in entry)


class MultiplicityRenameStep:
    id = "d9-multiplicity-rename"
    version = 1
    description = f"Rename diagram connections[].{_LEGACY_KEY} to {_CURRENT_KEY}"
    scanned_surface: ScannedSurface = "diagram_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for rel in list_frontmatter_candidate_files(view):
            content = view.read_text(rel)
            if content is None or not opens_with_frontmatter(content):
                continue
            frontmatter = extract_yaml_block(content)
            if not isinstance(frontmatter, dict):
                continue
            if str(frontmatter.get("artifact-type", "")) != "diagram":
                continue
            count = _legacy_key_count(frontmatter)
            if not count:
                continue
            plural = "y" if count == 1 else "ies"
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"legacy-{_LEGACY_KEY}:{rel}",
                    location=rel,
                    description=f"{count} diagram connections entr{plural} use the legacy '{_LEGACY_KEY}' key",
                    severity="warning",
                    auto_migratable=True,
                    rewrite_summary=f"rename '{_LEGACY_KEY}' -> '{_CURRENT_KEY}' in {count} entr{plural}",
                )
            )
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            content = view.read_text(finding.location)
            if content is None:
                outcomes.append(AppliedFinding(finding=finding, outcome="error", detail="file no longer exists"))
                continue
            rewritten = self._rewrite(content)
            writer.write_text(finding.location, rewritten)
            outcomes.append(AppliedFinding(finding=finding, outcome="applied"))
        return outcomes

    def _rewrite(self, content: str) -> str:
        reading = read_frontmatter(content)
        if not isinstance(reading, Frontmatter):
            return content
        return replace_frontmatter_text(content, _LEGACY_KEY_TOKEN_RE.sub(_CURRENT_KEY, reading.text))
