"""Reconciliation reporter for named profile conflicts (WU-R1).

Detect-only and non-destructive — mirroring ``DefaultSchemataEnsureStep``'s contract, it
never rewrites operator content. For every specialization the repo declares that binds
named profiles — entity and connection alike — it resolves the effective schema and reports
each incompatible-type conflict as a quarantined ``(type, specialization)`` pair (the
profiles/field/types are named in the merge message). Proposed resolutions (rename /
align-type / unbind, and safe auto-migration) are WU-R2.

Content-version DRIFT (a shipped profile advanced past a repo customisation — what P4's
per-profile ``version`` exists for) is NOT reported here yet: no reusable profiles are
shipped, so there is no baseline to drift from. When shipped profiles land, the drift
comparison activates by giving this step the shipped registry (the same way
``known_entity_type_names`` reaches a step — an ``RepoUpgradeView`` property fed by the
module registry through the adapter).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.application.artifacts.schema import (
    compute_effective_attribute_schema,
    compute_effective_connection_metadata_schema,
)
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.ontology_representation.profile_conflict_resolution import (
    propose_conflict_resolution,
    resolution_instructions,
)
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.specializations import (
    ConceptKind,
    SpecializationCatalog,
    SpecializationInfo,
    specialization_catalog_from_mapping,
)
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.yaml_documents import parse_yaml

_SPECIALIZATIONS = ".arch-repo/specializations.yaml"

#: Both concept kinds are scanned: a connection specialization binds profiles on the same
#: terms as an entity one, so leaving connections out would report half the conflicts.
_RESOLVERS: dict[ConceptKind, Callable[..., tuple[dict[str, Any] | None, list[str]]]] = {
    "entity": compute_effective_attribute_schema,
    "connection": compute_effective_connection_metadata_schema,
}


class ProfileReconciliationScanStep:
    id = "profile-reconciliation-scan"
    version = 1
    description = "Report named-profile conflicts (quarantined type/specialization pairs)"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        specializations = _repo_specializations(view)
        if specializations is None:
            return []
        findings: list[UpgradeFinding] = []
        for entry in specializations.entries:
            if not entry.bound_profiles:
                continue
            resolve = _RESOLVERS[entry.concept_kind]
            _schema, conflicts = resolve(
                view.root,
                entry.parent_type,
                [entry.slug],
                specialization_catalog=specializations,
                profile_registry=ProfileRegistry.empty(),  # repo profiles.yaml is read internally
            )
            for index, message in enumerate(conflicts):
                findings.append(self._finding(entry, index, message))
        return findings

    def _finding(self, entry: SpecializationInfo, index: int, message: str) -> UpgradeFinding:
        pair = f"{entry.parent_type}/{entry.slug}"
        subjects = "Entities" if entry.concept_kind == "entity" else "Connections"
        blocked = f"{subjects} of {pair} cannot be created or edited until the conflict is cleared."
        resolution = propose_conflict_resolution(message, bound_profiles=entry.bound_profiles)
        proposals = resolution_instructions(
            resolution,
            fallback=(
                "Resolve the conflicting named profiles (rename the attribute, align its type, or "
                "unbind one profile from this specialization), then re-run."
            ),
        )
        # ``propose_conflict_resolution`` never auto-migrates (no shipped baseline exists to
        # advance from), so every finding stays manual — the report-only contract.
        return UpgradeFinding(
            step_id=self.id,
            # The kind is part of the identity: an entity and a connection may each declare
            # the same parent-type/slug pair.
            finding_id=f"profile-conflict:{entry.concept_kind}:{pair}:{index}",
            location=_SPECIALIZATIONS,
            description=f"{entry.concept_kind} {pair} is quarantined by a profile conflict — {message}",
            severity="warning",
            auto_migratable=False,
            manual_instructions=f"{proposals} {blocked}",
        )

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding]
    ) -> list[AppliedFinding]:
        return []  # report-only: every finding is manual (auto_migratable=False)


def _repo_specializations(view: RepoUpgradeView) -> SpecializationCatalog | None:
    text = view.read_text(_SPECIALIZATIONS)
    if text is None:
        return None
    try:
        loaded: object = parse_yaml(text) or {}
    except yaml.YAMLError:
        return None  # a malformed specializations file is the specialization scan's finding, not ours
    if not isinstance(loaded, dict):
        return None
    return specialization_catalog_from_mapping(loaded, module_alias="repo")
