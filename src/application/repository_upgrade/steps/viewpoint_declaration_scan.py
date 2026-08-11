"""Read-only detector for `.arch-repo/viewpoints.yaml` (D7/D8): flags a declarations file
that fails to parse, mirroring `SpecializationDeclarationScanStep` for the other new
two-tier customization file. `viewpoint_catalog_from_mapping` already rejects unknown keys
and malformed enum values loudly at load time — this step turns that same check into a
proactive `arch-repair upgrade` finding instead of a crash the first time something loads it.

Always manual, for the same reason as the specialization declarations scan.
"""

from __future__ import annotations

from typing import Any

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.domain.yaml_documents import parse_yaml

_PATH = ".arch-repo/viewpoints.yaml"


class ViewpointDeclarationScanStep:
    id = "viewpoint-declaration-scan"
    version = 1
    description = f"Flag a {_PATH} that fails to parse"
    scanned_surface: ScannedSurface = "customizations"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        content = view.read_text(_PATH)
        if content is None:
            return []
        try:
            loaded: Any = parse_yaml(content) or {}
            if not isinstance(loaded, dict):
                raise ValueError("top-level YAML value must be a mapping")
            viewpoint_catalog_from_mapping(loaded)
        except Exception as exc:  # noqa: BLE001 — any parse failure is the signal this step exists for
            return [
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"malformed-viewpoints:{_PATH}",
                    location=_PATH,
                    description=f"{_PATH} does not parse as a valid viewpoint declarations file: {exc}",
                    severity="warning",
                    auto_migratable=False,
                    manual_instructions=(
                        f"{_PATH} failed to parse ({exc}). Review and repair by hand — a malformed "
                        "viewpoint definition can silently disable a viewpoint this repo depends on."
                    ),
                )
            ]
        return []

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        return []  # unreachable: every finding this step produces is auto_migratable=False
