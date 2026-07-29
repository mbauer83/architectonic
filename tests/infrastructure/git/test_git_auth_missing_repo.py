"""Credential probing must tolerate a configured repo that isn't on disk yet.

Regression: find_git_repos() returns the paths declared in arch-workspace.yaml,
which may not be cloned yet (arch-init runs before the backend in real
deployments, but not in every harness). Probing such a path previously crashed
with FileNotFoundError because subprocess.run(cwd=<missing>) cannot chdir.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.git.git_auth import collect_credentials, detect_remote_protocol


def test_detect_remote_protocol_returns_none_for_missing_path(tmp_path: Path) -> None:
    assert detect_remote_protocol(tmp_path / "not-cloned-yet") is None


def test_collect_credentials_skips_missing_repo_paths(tmp_path: Path) -> None:
    # Must return None (nothing to authenticate) rather than raising.
    assert collect_credentials([tmp_path / "absent"]) is None
