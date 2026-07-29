"""WU-Q1: Class A profile-registry validation at startup — engagement hard-fails,
enterprise logs and continues, only attached repos are read."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.backend._profile_registry_startup import validate_profile_registries


def _write_profiles(repo_root: Path, text: str) -> None:
    (repo_root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    (repo_root / ".arch-repo" / "profiles.yaml").write_text(text, encoding="utf-8")


def _write_specializations(repo_root: Path, text: str) -> None:
    (repo_root / ".arch-repo").mkdir(parents=True, exist_ok=True)
    (repo_root / ".arch-repo" / "specializations.yaml").write_text(text, encoding="utf-8")


def test_clean_engagement_does_not_abort(tmp_path: Path) -> None:
    # No registry file at all is the valid empty state.
    validate_profile_registries(tmp_path, None)


def test_malformed_engagement_registry_aborts_startup(tmp_path: Path) -> None:
    _write_profiles(tmp_path, "profile_schema: 99\nprofiles: {}\n")
    with pytest.raises(SystemExit):
        validate_profile_registries(tmp_path, None)


def test_same_defect_in_enterprise_does_not_abort(tmp_path: Path) -> None:
    engagement = tmp_path / "eng"
    enterprise = tmp_path / "ent"
    engagement.mkdir()
    enterprise.mkdir()
    _write_profiles(enterprise, "profile_schema: 99\nprofiles: {}\n")
    # Engagement is clean; the enterprise defect only warns — no SystemExit.
    validate_profile_registries(engagement, enterprise)


def test_undefined_binding_in_engagement_aborts_startup(tmp_path: Path) -> None:
    _write_profiles(tmp_path, "profile_schema: 1\nprofiles: {}\n")
    _write_specializations(
        tmp_path,
        "specializations:\n"
        "  entity:\n"
        "    application-component:\n"
        "      - slug: my-service\n"
        "        profiles: [ghost-profile]\n",
    )
    with pytest.raises(SystemExit):
        validate_profile_registries(tmp_path, None)


def test_unattached_repo_is_never_read(tmp_path: Path) -> None:
    # A broken registry in a directory that is neither the engagement nor enterprise root is
    # never touched: passing only a clean engagement root must not abort.
    engagement = tmp_path / "eng"
    engagement.mkdir()
    unattached = tmp_path / "somewhere-else"
    _write_profiles(unattached, "profile_schema: 99\nprofiles: {}\n")
    validate_profile_registries(engagement, None)
