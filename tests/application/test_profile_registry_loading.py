"""Tests for the optional repo-level profile-registry loader and the module-shipped
registry — including the regression guard that an existing repo (no registry file) is a
valid 'no named profiles' state."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.profile_registry_loading import load_repo_profile_registry
from src.domain.ontology_representation.profile_registry import ProfileRegistryError


def _write(repo_root: Path, text: str) -> None:
    (repo_root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    (repo_root / ".arch-repo" / "profiles.yaml").write_text(text, encoding="utf-8")


def test_absent_file_is_the_no_named_profiles_state(tmp_path: Path) -> None:
    # An existing repository with no registry file must load cleanly as empty.
    registry = load_repo_profile_registry(tmp_path)
    assert dict(registry.profiles) == {}


def test_valid_repo_registry_loads(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "profile_schema: 1\n"
        "profiles:\n"
        "  local-p:\n"
        "    version: 1\n"
        "    attributes:\n"
        "      X: {type: string}\n",
    )
    registry = load_repo_profile_registry(tmp_path)
    profile = registry.get("local-p")
    assert profile is not None
    assert profile.version == 1


def test_unknown_format_version_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "profile_schema: 99\nprofiles: {}\n")
    with pytest.raises(ProfileRegistryError, match="unsupported profile_schema 99"):
        load_repo_profile_registry(tmp_path)


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "")
    with pytest.raises(ProfileRegistryError, match="profile registry file is empty"):
        load_repo_profile_registry(tmp_path)


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "profile_schema: 1\nprofiles: {unterminated\n")
    with pytest.raises(ProfileRegistryError, match="cannot read profile registry"):
        load_repo_profile_registry(tmp_path)


def test_shipped_module_registry_is_reachable_and_carries_the_aibom_profiles() -> None:
    # Every ontology module exposes a profile registry; the shipped archimate-4 one now
    # carries the AIBOM shared profiles (WU-A2). The mechanism resolves them by name.
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    catalogs = build_runtime_catalogs(build_module_registry())
    assert catalogs.profiles.get("ai-supplier") is not None
    assert catalogs.profiles.get("ai-licensing") is not None
    for module in catalogs.module_catalog.all_ontologies().values():
        assert module.profile_registry is not None
