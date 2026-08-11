"""Read-only detector for `.arch-repo/specializations.yaml` (D4/D6): flags a declarations
file that fails to parse, so drift in this new, repo-local customization file surfaces in
`arch-repair upgrade` even when the full backend/verifier never runs against this repo.

Always manual: a malformed declarations file has no single unambiguous auto-rewrite (the
author's intent for the broken entry isn't recoverable), so this step only ever reports.
"""

from __future__ import annotations

from typing import Any

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.ontology_representation.specializations import specialization_catalog_from_mapping
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.yaml_documents import parse_yaml

_PATH = ".arch-repo/specializations.yaml"


class SpecializationDeclarationScanStep:
    id = "specialization-declaration-scan"
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
            specialization_catalog_from_mapping(loaded, module_alias="arch-repair-upgrade-scan")
        except Exception as exc:  # noqa: BLE001 — any parse failure is the signal this step exists for
            return [
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"malformed-specializations:{_PATH}",
                    location=_PATH,
                    description=f"{_PATH} does not parse as a valid specialization declarations file: {exc}",
                    severity="warning",
                    auto_migratable=False,
                    manual_instructions=(
                        f"{_PATH} failed to parse ({exc}). Review and repair by hand — a malformed "
                        "specialization declaration can silently disable specializations this repo depends on."
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
