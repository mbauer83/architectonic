"""The roots the backend serves are absolute, however they were given."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.backend import server_roots


def test_relative_command_line_roots_are_resolved_against_the_start_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCH_REPO_ROOT", raising=False)
    monkeypatch.delenv("ARCH_ENTERPRISE_ROOT", raising=False)

    engagement, enterprise = server_roots.resolve_server_roots("engagements/E/architecture-repository", "ent")

    assert engagement == tmp_path / "engagements" / "E" / "architecture-repository"
    assert enterprise == tmp_path / "ent"


def test_relative_environment_roots_are_resolved_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARCH_REPO_ROOT", "eng")
    monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", "ent")

    assert server_roots.resolve_server_roots(None, None) == (tmp_path / "eng", tmp_path / "ent")
