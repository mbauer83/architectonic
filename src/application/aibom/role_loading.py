"""Resolve AIBOM derivation-role bindings for a repository: the module-shipped defaults with
an optional ``.arch-repo/aibom-roles.yaml`` override merged per-role over them.

The override file is OPTIONAL — its absence means "use the shipped bindings", the state
every repository is in until it declares different modelling conventions. A present but
malformed file, or one naming a role outside the closed vocabulary, is a ``DerivationRoleError``
(the parser's typed error) for the caller to report against the file.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.domain.assurance.aibom_roles import (
    DerivationRoleBindings,
    DerivationRoleError,
    merge_role_bindings,
    role_bindings_from_mapping,
)
from src.domain.yaml_documents import parse_yaml

REPO_AIBOM_ROLES_PATH = ".arch-repo/aibom-roles.yaml"


def resolve_aibom_role_bindings(repo_root: Path, shipped: DerivationRoleBindings) -> DerivationRoleBindings:
    """``shipped`` (the module defaults) with the repo's per-role overrides applied. The repo
    file is optional; when absent the shipped bindings are returned unchanged."""
    path = repo_root / REPO_AIBOM_ROLES_PATH
    if not path.is_file():
        return shipped
    label = str(path)
    try:
        raw = parse_yaml(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DerivationRoleError(f"{label}: cannot read AIBOM role bindings: {exc}") from exc
    if raw is None:
        raise DerivationRoleError(f"{label}: AIBOM role bindings file is empty")
    override = role_bindings_from_mapping(raw, label=label)
    return merge_role_bindings(shipped, override)
