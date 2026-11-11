"""`arch-repair upgrade --commit` writes the tiers a deployment owns, and records what it wrote (B81).

A container upgraded its cloned enterprise mirror in place and left the migration in the working tree,
so the next start's `arch-init` refused the dirty clone: the container could not start a second time.
The enterprise tier is maintained upstream; the deployment only pulls it, and a backend reads the older
format correctly. So the upgrade evaluates and reports that tier and leaves it alone unless the
deployment owns it (`--admin-mode`, as for the backend). What it does write is committed as one
recognisable commit where that is unambiguous — the repository is its own and was clean.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.cli import _upgrade_tiers as tiers
from src.infrastructure.cli import arch_repair_upgrade as cli
from tests.cli.test_arch_repair_upgrade_deployment import _init_repo, _repo_registry


@pytest.fixture(autouse=True)
def _no_real_backend(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: False)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def _clean(repo: Path) -> bool:
    return _git(repo, "status", "--porcelain") == ""


def _lagging_deployment(tmp_path: Path) -> tuple[Path, Path]:
    """An engagement clone and an enterprise mirror, both at the old format and both clean."""
    engagement, enterprise = tmp_path / "engagement", tmp_path / "enterprise"
    _init_repo(engagement)
    _init_repo(enterprise)
    return engagement, enterprise


def _upgrade(*args: str) -> int:
    return cli.main_upgrade([*args, "--commit"], registry=_repo_registry())


def test_a_second_start_over_a_lagging_enterprise_remote_finds_both_tiers_clean(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    engagement, enterprise = _lagging_deployment(tmp_path)
    enterprise_head = _git(enterprise, "rev-parse", "HEAD")

    assert _upgrade("--repo-root", str(engagement), "--enterprise-root", str(enterprise)) == 0

    assert (engagement / "current.txt").exists(), "the engagement was not upgraded"
    assert _clean(engagement), "the engagement's migration was left in the working tree"
    assert _git(engagement, "log", "-1", "--format=%s").startswith("Upgrade the persisted repository format")
    assert not (enterprise / "current.txt").exists(), "the enterprise mirror was written"
    assert _clean(enterprise) and _git(enterprise, "rev-parse", "HEAD") == enterprise_head
    assert "does not own the enterprise tier" in capsys.readouterr().err

    # The restart: everything `arch-init` checks is clean, and the upgrade is a no-op.
    assert _upgrade("--repo-root", str(engagement), "--enterprise-root", str(enterprise)) == 0
    assert _clean(engagement) and _clean(enterprise)


def test_admin_mode_owns_the_enterprise_tier_and_upgrades_it(tmp_path: Path) -> None:
    engagement, enterprise = _lagging_deployment(tmp_path)

    assert _upgrade("--repo-root", str(engagement), "--enterprise-root", str(enterprise), "--admin-mode") == 0

    assert (enterprise / "current.txt").exists()
    assert _clean(enterprise)


def test_a_workspace_enterprise_root_is_an_enterprise_tier(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engagement, enterprise = _lagging_deployment(tmp_path)
    monkeypatch.setattr(
        tiers, "load_init_state",
        lambda _ws: {"engagement_root": str(engagement), "enterprise_root": str(enterprise)},
    )

    assert _upgrade("--workspace", str(tmp_path)) == 0

    assert (engagement / "current.txt").exists()
    assert not (enterprise / "current.txt").exists()


def test_a_tree_with_the_operators_own_changes_is_written_and_not_committed(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    engagement, _ = _lagging_deployment(tmp_path)
    (engagement / "notes.txt").write_text("the operator's own work", encoding="utf-8")
    head = _git(engagement, "rev-parse", "HEAD")

    assert _upgrade("--repo-root", str(engagement)) == 0

    assert (engagement / "current.txt").exists()
    assert _git(engagement, "rev-parse", "HEAD") == head, "the operator's change was folded into a commit"
    assert "already had changes" in capsys.readouterr().err


def test_a_repository_inside_another_is_written_and_not_committed(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    outer = tmp_path / "product"
    _init_repo(outer)
    inner = outer / "engagements" / "eng"
    inner.mkdir(parents=True)
    (inner / "legacy.txt").write_text("hello", encoding="utf-8")
    _git(outer, "add", "-A")
    _git(outer, "commit", "-q", "-m", "nested engagement")
    head = _git(outer, "rev-parse", "HEAD")

    assert _upgrade("--repo-root", str(inner)) == 0

    assert (inner / "current.txt").exists()
    assert _git(outer, "rev-parse", "HEAD") == head, "a commit was made in somebody else's repository"
    assert "not its own repository" in capsys.readouterr().err
