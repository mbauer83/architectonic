"""Tests for artifact_write_cli.py — _default_repo_root and main() error paths.

Covers: _default_repo_root returning None when no init state,
main() parser error when no --repo-root provided, and
main() early return when backend not running.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.infrastructure.write.artifact_write_cli import _default_repo_root, main


class TestDefaultRepoRoot:
    def test_returns_none_when_no_state(self) -> None:
        with patch("src.infrastructure.write.artifact_write_cli.load_init_state", return_value=None):
            result = _default_repo_root()
        assert result is None

    def test_returns_path_when_state_present(self, tmp_path) -> None:
        with patch("src.infrastructure.write.artifact_write_cli.load_init_state",
                   return_value={"engagement_root": str(tmp_path)}):
            result = _default_repo_root()
        assert result == tmp_path


class TestMainErrors:
    def test_no_repo_root_causes_parser_error(self) -> None:
        with patch("src.infrastructure.write.artifact_write_cli._default_repo_root", return_value=None):
            with pytest.raises(SystemExit):
                main(["delete-entity", "REQ@1.AA.test"])

    def test_backend_not_running_returns_1(self, tmp_path) -> None:
        with patch("src.infrastructure.write.artifact_write_cli.read_backend_state", return_value=None):
            result = main(["--repo-root", str(tmp_path), "delete-entity", "REQ@1.AA.test"])
        assert result == 1

    def test_backend_probe_fails_returns_1(self, tmp_path) -> None:
        with patch("src.infrastructure.write.artifact_write_cli.read_backend_state",
                   return_value={"pid": 1, "port": 9999}):
            with patch("src.infrastructure.write.artifact_write_cli.probe_backend", return_value=False):
                result = main(["--repo-root", str(tmp_path), "delete-entity", "REQ@1.AA.test"])
        assert result == 1
