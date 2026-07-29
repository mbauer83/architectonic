"""Mark on-disk attribute schemata whose enums are ranked.

An attribute schema in a repository is a file the operator owns. The shipped defaults now declare
which of their enums are in ascending rank order, and without that marker an existing repo's copy
sorts a severity alphabetically — quietly, and in the direction that makes `catastrophic` look
milder than `minor`.

Three cases, and the distinction between the last two is the whole reason this is a step rather
than an overwrite:

* **The on-disk enum matches the shipped one and lacks the marker.** Adding it changes no value and
  no ordering that was ever intended; migrated automatically.
* **The on-disk enum has drifted from the shipped one.** Reported as a manual finding describing
  what to add and why, and nothing is rewritten. Following the existing rule that a local edit is
  never overwritten and never silently drifts out of sight — the members are what an operator would
  have customised, and re-ranking somebody's own vocabulary is not this step's business.
* **The marker is already present.** Nothing to do, and a second run must be byte-stable.

Drift is not always an operator's doing: a repo can carry members a later release retired. The
finding says which members differ in each direction, so a reader can tell the two apart rather than
being told only that their file is "different".
"""

from __future__ import annotations

import json
from typing import Any

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.ontology_representation.attribute_scales import ORDINAL_SCALE, SCALE_KEYWORD
from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_SCHEMA_DIR = ".arch-repo/schemata"

#: The shipped defaults' formatting, so an upgraded file differs only by the added marker.
_INDENT = 2


def _ranked_properties(schema: Any) -> dict[str, tuple[str, ...]]:
    """Property name → ranked members, for every property the shipped default marks ordinal."""
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    return {
        str(name): tuple(str(v) for v in prop.get("enum", ()))
        for name, prop in properties.items()
        if isinstance(prop, dict) and prop.get(SCALE_KEYWORD) == ORDINAL_SCALE
    }


def _on_disk(view: RepoUpgradeView, filename: str) -> dict[str, Any] | None:
    content = view.read_text(f"{_SCHEMA_DIR}/{filename}")
    if content is None:
        return None
    try:
        loaded = json.loads(content)
    except json.JSONDecodeError:
        # A malformed schema file is the schema-scan step's finding, not this one's.
        return None
    return loaded if isinstance(loaded, dict) else None


def _describe_drift(shipped: tuple[str, ...], present: tuple[str, ...]) -> str:
    retired = [value for value in present if value not in shipped]
    added = [value for value in shipped if value not in present]
    if retired or added:
        parts = []
        if retired:
            parts.append(f"this file has {', '.join(retired)}, which the shipped set no longer does")
        if added:
            parts.append(f"the shipped set has {', '.join(added)}, which this file does not")
        return "; ".join(parts)
    return "the same members are listed in a different order, so their ranks would differ"


class OrdinalEnumDeclarationStep:
    id = "ordinal-enum-declaration"
    version = 1
    description = "Mark on-disk attribute enums that the shipped defaults rank as ordinal"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for filename, shipped_schema in sorted(DEFAULT_SCHEMATA.items()):
            ranked = _ranked_properties(shipped_schema)
            if not ranked:
                continue
            present = _on_disk(view, filename)
            if present is None:
                # Absent entirely — the ensure-missing step ships it, marker already present.
                continue
            properties = present.get("properties")
            if not isinstance(properties, dict):
                continue
            for name, shipped_members in sorted(ranked.items()):
                prop = properties.get(name)
                if not isinstance(prop, dict) or prop.get(SCALE_KEYWORD) == ORDINAL_SCALE:
                    continue
                on_disk_members = tuple(str(v) for v in prop.get("enum", ()))
                matches = on_disk_members == shipped_members
                drift = (
                    "" if matches
                    else f" — and its members have drifted: {_describe_drift(shipped_members, on_disk_members)}"
                )
                findings.append(UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"unranked-enum:{filename}:{name}",
                    location=f"{_SCHEMA_DIR}/{filename}",
                    description=(
                        f"'{name}' is a ranked scale in the shipped default but this copy does not "
                        f"declare it, so its values sort alphabetically rather than by rank{drift}"
                    ),
                    severity="warning" if matches else "error",
                    auto_migratable=matches,
                    rewrite_summary=(
                        f"add '{SCALE_KEYWORD}: {ORDINAL_SCALE}' to '{name}'" if matches else None
                    ),
                    manual_instructions=None if matches else (
                        f"Reconcile '{name}' with the shipped vocabulary "
                        f"({', '.join(shipped_members)}), then add "
                        f"\"{SCALE_KEYWORD}\": \"{ORDINAL_SCALE}\" to it. The marker is not added "
                        "automatically here because the members differ: ranking a list this "
                        "software did not define would assign an order nobody chose."
                    ),
                ))
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        applied: list[AppliedFinding] = []
        by_file: dict[str, list[UpgradeFinding]] = {}
        for finding in findings:
            if finding.auto_migratable:
                by_file.setdefault(finding.finding_id.split(":")[1], []).append(finding)
            else:
                applied.append(AppliedFinding(
                    finding=finding, outcome="skipped", detail="members differ from the shipped set",
                ))
        for filename, file_findings in sorted(by_file.items()):
            present = _on_disk(view, filename)
            if present is None:
                applied.extend(
                    AppliedFinding(finding=f, outcome="error", detail="file no longer parses")
                    for f in file_findings
                )
                continue
            properties = present.get("properties")
            if not isinstance(properties, dict):
                continue
            for finding in file_findings:
                name = finding.finding_id.split(":")[2]
                prop = properties.get(name)
                if isinstance(prop, dict):
                    prop[SCALE_KEYWORD] = ORDINAL_SCALE
            writer.write_text(
                f"{_SCHEMA_DIR}/{filename}",
                json.dumps(present, indent=_INDENT, ensure_ascii=False) + "\n",
            )
            applied.extend(AppliedFinding(finding=f, outcome="applied") for f in file_findings)
        return applied
