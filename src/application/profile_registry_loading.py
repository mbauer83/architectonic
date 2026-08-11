"""Load an optional repo-level named-profile registry from ``.arch-repo/profiles.yaml``.

A repository may ship its own named profiles alongside the module-shipped ones; the file is
OPTIONAL — its absence is the valid "no named profiles" state every existing repository is
in (P1 regression guard). A present-but-malformed file is a Class A structural error and
raises ``ProfileRegistryError`` for the caller (startup/CLI) to report against the file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.domain.ontology_representation.profile_registry import (
    ProfileRegistry,
    ProfileRegistryError,
    profile_registry_from_mapping,
)
from src.domain.yaml_documents import parse_yaml

REPO_PROFILE_REGISTRY_PATH = ".arch-repo/profiles.yaml"


def load_repo_profile_registry(repo_root: Path) -> ProfileRegistry:
    """The repository's named-profile registry, or an empty registry when the file is
    absent. Raises ``ProfileRegistryError`` if the file exists but cannot be read or parsed."""
    path = repo_root / REPO_PROFILE_REGISTRY_PATH
    if not path.is_file():
        return ProfileRegistry.empty()
    label = str(path)
    try:
        raw = parse_yaml(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ProfileRegistryError(f"cannot read profile registry: {exc}", label=label) from exc
    if raw is None:
        raise ProfileRegistryError("profile registry file is empty", label=label)
    return profile_registry_from_mapping(raw, label=label)
