"""Startup-time named-profile-registry validation for the backend composition root (WU-Q1).

Class A (structural) failures — a malformed/unknown-version ``.arch-repo/profiles.yaml`` or a
specialization binding a profile the effective registry does not define — make the profile
subsystem untrustworthy, so they follow the same tier posture as the group registry
(``_group_registry_startup``): the engagement (writable) repo hard-fails startup; an attached
enterprise (read-only) repo logs and continues. Only attached repos are read — never a
filesystem scan (PLAN §3 P6). Class B (scoped) conflicts do NOT abort here; they are
quarantined at the write boundary (WU-Q2/Q3).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _class_a_findings(repo_root: Path) -> list[str]:
    """Every Class A finding for one attached repo: a malformed registry (caught and reported,
    never raised) and each undefined binding across the module ∪ repo-level specializations."""
    from src.application.profile_registry_loading import load_repo_profile_registry
    from src.domain.ontology_representation.profile_registry import ProfileRegistryError, unresolved_profile_bindings
    from src.infrastructure.app_bootstrap import (
        get_module_registry,
        process_runtime_catalogs,
        registered_meta_ontology_values,
    )
    from src.infrastructure.specialization_declarations import load_specialization_catalog_file

    try:
        repo_registry = load_repo_profile_registry(repo_root)
    except ProfileRegistryError as exc:
        return [str(exc)]

    catalogs = process_runtime_catalogs()
    effective_registry = catalogs.profiles.overlay(repo_registry)

    specializations = list(catalogs.specializations.entries)
    for alias in registered_meta_ontology_values(get_module_registry()):
        specializations.extend(load_specialization_catalog_file(repo_root, alias).entries)

    bindings = [
        (f"specialization {spec.parent_type}/{spec.slug}", spec.bound_profiles)
        for spec in specializations
        if spec.bound_profiles
    ]
    # The repo's specializations.yaml is read once per meta-ontology alias, so a repo-defined
    # binding can appear under several aliases — dedup the findings to one line each.
    return list(dict.fromkeys(unresolved_profile_bindings(bindings, effective_registry)))


def validate_profile_registries(repo_root_path: Path, enterprise_root_path: Path | None) -> None:
    """Validate the attached repos' profile registries before the index build. Engagement
    Class A → abort; enterprise Class A → warn and continue."""
    findings = _class_a_findings(repo_root_path)
    if findings:
        joined = "\n".join(findings)
        logger.error(
            "Startup aborted — attribute profile registry error(s):\n%s\n"
            "Fix .arch-repo/profiles.yaml (or the offending specialization binding) and restart.",
            joined,
        )
        sys.exit(1)

    if enterprise_root_path is not None:
        enterprise_findings = _class_a_findings(enterprise_root_path)
        if enterprise_findings:
            logger.warning(
                "Enterprise attribute profile registry has errors (server will start; fix when possible):\n%s",
                "\n".join(enterprise_findings),
            )
