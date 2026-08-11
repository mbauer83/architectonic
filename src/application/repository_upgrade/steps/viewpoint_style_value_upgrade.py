"""Migrate viewpoint presentation style values that predate per-capability validation.

Style values were opaque strings; anything a renderer did not recognize painted as the
neutral fallback. Save-time validation now rejects out-of-vocabulary values (semantic
tokens, named scale endpoints, or ``#rrggbb`` colors per capability), so a definition
carrying legacy values could no longer be re-saved unchanged. This step rewrites those
values to ``neutral`` — byte-identical to what they already rendered as — and leaves a
per-definition record of every replacement so authors can pick real colors afterwards.

The rewrite re-serializes ``viewpoints.yaml`` through the same domain mapping +
``yaml.safe_dump(..., sort_keys=False)`` the authoring save path uses, so an upgraded
file is exactly what the next GUI/MCP save would produce anyway.
"""

from __future__ import annotations

from typing import Any

import yaml  # type: ignore[import-untyped]

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.domain.viewpoints.viewpoint_serialization import viewpoint_catalog_to_mapping
from src.domain.viewpoints.viewpoint_style_normalization import normalize_definition_style_values
from src.domain.viewpoints.viewpoints import ViewpointCatalog
from src.domain.yaml_documents import parse_yaml

_PATH = ".arch-repo/viewpoints.yaml"


def _parsed_catalog(view: RepoUpgradeView) -> ViewpointCatalog | None:
    content = view.read_text(_PATH)
    if content is None:
        return None
    try:
        loaded: Any = parse_yaml(content) or {}
        if not isinstance(loaded, dict):
            return None
        return viewpoint_catalog_from_mapping(loaded)
    except Exception:  # noqa: BLE001 — a malformed file is the declaration scan step's finding
        return None


class ViewpointStyleValueUpgradeStep:
    id = "viewpoint-style-value-normalize"
    version = 1
    description = f"Rewrite pre-validation presentation style values in {_PATH} to 'neutral'"
    scanned_surface: ScannedSurface = "customizations"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        catalog = _parsed_catalog(view)
        if catalog is None:
            return []
        findings: list[UpgradeFinding] = []
        for definition in catalog.entries:
            _, replaced = normalize_definition_style_values(definition)
            if not replaced:
                continue
            listed = "; ".join(replaced)
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"legacy-style-values:{definition.slug}",
                    location=_PATH,
                    description=(
                        f"viewpoint '{definition.slug}' carries {len(replaced)} presentation style "
                        f"value(s) outside the validated vocabulary ({listed}); they render as the "
                        "neutral fallback today and would be rejected on the next save"
                    ),
                    severity="error",
                    auto_migratable=True,
                    rewrite_summary=(
                        f"viewpoint '{definition.slug}': rewrite {len(replaced)} style value(s) to "
                        "'neutral' (their current rendered color); pick semantic tokens or '#rrggbb' "
                        "colors afterwards"
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
        catalog = _parsed_catalog(view)
        if catalog is None:
            return [
                AppliedFinding(finding=finding, outcome="error", detail="file no longer parses")
                for finding in findings
            ]
        normalized = ViewpointCatalog(
            entries=tuple(normalize_definition_style_values(definition)[0] for definition in catalog.entries)
        )
        text = str(yaml.safe_dump(viewpoint_catalog_to_mapping(normalized), sort_keys=False))
        writer.write_text(_PATH, text)
        return [AppliedFinding(finding=finding, outcome="applied") for finding in findings]
