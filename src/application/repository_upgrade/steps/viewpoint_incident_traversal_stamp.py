"""Stamp the implicit incident-predicate traversal explicitly in saved viewpoints.

An incident condition saved without a ``traversal`` key has always executed as ``direct``,
but the meaning lived in the parser default rather than in the file — a future default
change would silently alter every saved recipe. Serialization now always writes the
predicate's traversal; this step brings pre-change files up to that contract by
re-serializing through the same domain mapping + ``yaml.safe_dump(..., sort_keys=False)``
the authoring save path uses. Pure stamping: every predicate keeps its parsed value, so
the rewrite never changes what a definition matches.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import yaml  # type: ignore[import-untyped]

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.domain.viewpoints.viewpoint_serialization import viewpoint_catalog_to_mapping
from src.domain.viewpoints.viewpoints import ViewpointCatalog

_PATH = ".arch-repo/viewpoints.yaml"


def _unstamped_incident_count(node: object) -> int:
    """Incident mappings anywhere in a definition's raw structure that lack an explicit
    ``traversal`` key (entity criteria, endpoint criteria, bindings, presentation
    match criteria — the walk is structural, not schema-aware, so no site is missed)."""
    if isinstance(node, Mapping):
        own = 1 if node.get("kind") == "incident" and "traversal" not in node else 0
        return own + sum(_unstamped_incident_count(value) for value in node.values())
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        return sum(_unstamped_incident_count(item) for item in node)
    return 0


def _parsed(view: RepoUpgradeView) -> tuple[Mapping[str, object], ViewpointCatalog] | None:
    content = view.read_text(_PATH)
    if content is None:
        return None
    try:
        loaded: object = yaml.safe_load(content) or {}
        if not isinstance(loaded, Mapping):
            return None
        return loaded, viewpoint_catalog_from_mapping(loaded)
    except Exception:  # noqa: BLE001 — a malformed file is the declaration scan step's finding
        return None


class ViewpointIncidentTraversalStampStep:
    id = "viewpoint-incident-traversal-stamp"
    version = 1
    description = f"Write the implicit 'traversal: direct' explicitly on incident predicates in {_PATH}"
    scanned_surface: ScannedSurface = "customizations"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        parsed = _parsed(view)
        if parsed is None:
            return []
        raw, catalog = parsed
        del catalog  # parse succeeded — that is all detection needs from it
        count = _unstamped_incident_count(raw)
        if count == 0:
            return []
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id="implicit-incident-traversal",
                location=_PATH,
                description=(
                    f"{count} incident predicate(s) rely on the parser's implicit 'direct' traversal; "
                    "a future default change would silently alter what these saved recipes match"
                ),
                severity="warning",
                auto_migratable=True,
                rewrite_summary=(
                    f"stamp 'traversal: direct' explicitly on {count} incident predicate(s) — "
                    "pure stamping, no predicate changes meaning"
                ),
            )
        ]

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        parsed = _parsed(view)
        if parsed is None:
            return [
                AppliedFinding(finding=finding, outcome="error", detail="file no longer parses")
                for finding in findings
            ]
        _, catalog = parsed
        text = str(yaml.safe_dump(viewpoint_catalog_to_mapping(catalog), sort_keys=False))
        writer.write_text(_PATH, text)
        return [AppliedFinding(finding=finding, outcome="applied") for finding in findings]
