"""Group meta-ontology rename: migrate the legacy ``archimate-next`` meta-ontology alias
in ``.arch-repo/groups.yaml`` to its current name ``archimate-4``.

A model-project group's ``meta_ontology`` value must be one of the meta-ontology aliases the
running software registers. The ArchiMate ontology's alias was ``archimate-next`` in an
earlier release and is ``archimate-4`` now; a repo authored under the old name carries
``meta_ontology: archimate-next``, which the current group-registry validation rejects
outright (a hard startup error), so a repo predating the rename cannot be served until this
one value is migrated.

Like the diagram-frontmatter rename step, ``apply()`` replaces only the exact
``meta_ontology`` value token — scoped to that key — rather than reparsing and re-dumping the
YAML, so every other line (comments, ordering, quoting, any uncommitted edit this step has no
opinion about) is left byte-for-byte untouched.
"""

from __future__ import annotations

import re
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.yaml_documents import parse_yaml

_PATH = ".arch-repo/groups.yaml"
_LEGACY_VALUE = "archimate-next"
_CURRENT_VALUE = "archimate-4"

# Match `meta_ontology:` followed by the legacy value, tolerating optional surrounding
# quotes, so `meta_ontology: archimate-next`, `meta_ontology: "archimate-next"`, and the
# single-quoted form all rewrite. `\b` after the value keeps it from matching a longer token.
_VALUE_TOKEN_RE = re.compile(rf"""(meta_ontology:[ \t]*["']?){re.escape(_LEGACY_VALUE)}\b(["']?)""")


def _legacy_value_count(loaded: object) -> int:
    if not isinstance(loaded, dict):
        return 0
    projects = loaded.get("model-projects")
    if not isinstance(projects, list):
        return 0
    return sum(
        1 for entry in projects if isinstance(entry, dict) and entry.get("meta_ontology") == _LEGACY_VALUE
    )


class GroupMetaOntologyRenameStep:
    id = "group-meta-ontology-archimate-4-rename"
    version = 1
    description = f"Rename model-project meta_ontology '{_LEGACY_VALUE}' to '{_CURRENT_VALUE}' in {_PATH}"
    scanned_surface: ScannedSurface = "group_registry"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        content = view.read_text(_PATH)
        if content is None:
            return []
        try:
            loaded: Any = parse_yaml(content)
        except yaml.YAMLError:
            # A groups.yaml that doesn't parse is a different concern (surfaced by the
            # backend's own group-registry validation); this rename step stays silent on it.
            return []
        count = _legacy_value_count(loaded)
        if not count:
            return []
        plural = "" if count == 1 else "s"
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id=f"legacy-meta-ontology:{_PATH}",
                location=_PATH,
                description=(
                    f"{count} model-project group{plural} declare the legacy meta_ontology "
                    f"'{_LEGACY_VALUE}' (renamed to '{_CURRENT_VALUE}')"
                ),
                severity="error",
                auto_migratable=True,
                rewrite_summary=(
                    f"rename meta_ontology '{_LEGACY_VALUE}' -> '{_CURRENT_VALUE}' "
                    f"in {count} group{plural}"
                ),
            )
        ]

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
            rewritten = _VALUE_TOKEN_RE.sub(rf"\g<1>{_CURRENT_VALUE}\g<2>", content)
            writer.write_text(finding.location, rewritten)
            outcomes.append(AppliedFinding(finding=finding, outcome="applied"))
        return outcomes
