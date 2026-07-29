from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.infrastructure.cli import arch_repair
from src.infrastructure.git import repair_adapter
from src.infrastructure.git.git_auth import GitCredentials


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    (path / ".git").mkdir(parents=True)
    return path


def test_repair_wires_auth_and_runs_guarded_sequence(
    repo: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    env_seen: list[dict[str, str]] = []
    askpass = repo / "askpass.sh"
    askpass.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(
        arch_repair,
        "collect_credentials",
        lambda targets: GitCredentials(ssh_passphrase="ssh-secret"),
    )
    monkeypatch.setattr(arch_repair, "create_askpass_script", lambda: askpass)
    monkeypatch.setattr(
        arch_repair,
        "build_git_env",
        lambda credentials, script: {
            "SSH_ASKPASS": str(script),
            "ARCH_GIT_SSH_PASSWORD": credentials.ssh_passphrase or "",
        },
    )

    def fake_run_git(_repo, args, *, timeout, env):
        calls.append(tuple(args))
        env_seen.append(dict(env))
        return _result_for(args)

    monkeypatch.setattr(repair_adapter, "run_git", fake_run_git)

    result = arch_repair.execute_repair(
        repo=repo,
        repair_branch="repair/cps-rename",
        message="repair",
        confirm=True,
    )

    assert result.phase == "complete"
    assert ("fetch", "origin", "main") in calls
    # Stages the tree but excludes the transient M4 transaction journal.
    assert ("add", "-A", "--", ".", ":(exclude).arch-repo/transactions") in calls
    # Must NOT gate on `git diff --cached --check`: it false-fails on legitimate model
    # whitespace and Markdown setext underlines mistaken for conflict markers.
    assert ("diff", "--cached", "--check") not in calls
    assert ("push", "-u", "origin", "repair/cps-rename") in calls
    assert ("merge", "--ff-only", "repair/cps-rename") in calls
    assert ("push", "origin", "main") in calls
    assert all(env["ARCH_GIT_SSH_PASSWORD"] == "ssh-secret" for env in env_seen)
    assert not askpass.exists()


def test_repair_resumes_from_state_without_reinitializing_branch(
    repo: Path,
    monkeypatch,
) -> None:
    state_path = repo / ".git" / "arch-repair-state.json"
    state_path.write_text(
        '{"original_branch":"main","phase":"committed","repair_branch":"repair/cps"}\n',
        encoding="utf-8",
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(arch_repair, "collect_credentials", lambda targets: None)
    askpass = repo / "askpass.sh"
    askpass.write_text("", encoding="utf-8")
    monkeypatch.setattr(arch_repair, "create_askpass_script", lambda: askpass)
    monkeypatch.setattr(
        repair_adapter,
        "run_git",
        lambda _repo, args, *, timeout, env: (
            calls.append(tuple(args)),
            _result_for(args, repair_exists=True, no_staged_changes=True),
        )[1],
    )

    result = arch_repair.execute_repair(
        repo=repo,
        repair_branch="repair/cps",
        message="repair",
        confirm=True,
    )

    assert result.phase == "complete"
    assert ("switch", "repair/cps") in calls
    assert not any(call[:2] == ("switch", "-c") for call in calls)
    assert not any("commit" in call for call in calls)


def test_repair_rejects_unexpected_upstream(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(arch_repair, "collect_credentials", lambda targets: None)
    askpass = repo / "askpass.sh"
    askpass.write_text("", encoding="utf-8")
    monkeypatch.setattr(arch_repair, "create_askpass_script", lambda: askpass)
    monkeypatch.setattr(
        repair_adapter,
        "run_git",
        lambda _repo, args, *, timeout, env: SimpleNamespace(
            returncode=0,
            stdout="origin/wrong\n"
            if "--symbolic-full-name" in args
            else "main\n",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="Unexpected upstream"):
        arch_repair.execute_repair(
            repo=repo,
            repair_branch="repair/cps",
            message="repair",
            confirm=True,
        )


def test_token_file_is_registered_before_collecting_credentials(
    repo: Path,
    monkeypatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(
        arch_repair,
        "register_token_file",
        lambda path: order.append(f"token:{path}"),
    )

    def collect(_targets):
        order.append("collect")
        raise RuntimeError("stop")

    monkeypatch.setattr(arch_repair, "collect_credentials", collect)

    with pytest.raises(RuntimeError, match="stop"):
        arch_repair.execute_repair(
            repo=repo,
            repair_branch="repair/cps",
            message="repair",
            token_file="/run/secrets/git-token",
            confirm=True,
        )

    assert order == ["token:/run/secrets/git-token", "collect"]


def test_repair_requires_explicit_confirmation(repo: Path) -> None:
    with pytest.raises(ValueError, match="--confirm"):
        arch_repair.execute_repair(
            repo=repo,
            repair_branch="repair/cps",
            message="repair",
        )


def test_main_legacy_no_subcommand_is_deprecated_alias_for_git_repair(
    repo: Path,
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, ...]] = []
    askpass = repo / "askpass.sh"
    askpass.write_text("", encoding="utf-8")
    monkeypatch.setattr(arch_repair, "collect_credentials", lambda targets: None)
    monkeypatch.setattr(arch_repair, "create_askpass_script", lambda: askpass)
    monkeypatch.setattr(
        repair_adapter,
        "run_git",
        lambda _repo, args, *, timeout, env: (calls.append(tuple(args)), _result_for(args))[1],
    )

    exit_code = arch_repair.main(
        ["--repo-root", str(repo), "--repair-branch", "repair/legacy", "--message", "m", "--confirm"]
    )

    assert exit_code == 0
    assert ("push", "origin", "main") in calls
    assert "DEPRECATED" in capsys.readouterr().err


def test_main_explicit_git_repair_subcommand(repo: Path, monkeypatch, capsys) -> None:
    calls: list[tuple[str, ...]] = []
    askpass = repo / "askpass.sh"
    askpass.write_text("", encoding="utf-8")
    monkeypatch.setattr(arch_repair, "collect_credentials", lambda targets: None)
    monkeypatch.setattr(arch_repair, "create_askpass_script", lambda: askpass)
    monkeypatch.setattr(
        repair_adapter,
        "run_git",
        lambda _repo, args, *, timeout, env: (calls.append(tuple(args)), _result_for(args))[1],
    )

    exit_code = arch_repair.main(
        ["git-repair", "--repo-root", str(repo), "--repair-branch", "repair/x", "--message", "m", "--confirm"]
    )

    assert exit_code == 0
    assert ("push", "origin", "main") in calls
    assert "DEPRECATED" not in capsys.readouterr().err


def test_main_dispatches_upgrade_subcommand(monkeypatch) -> None:
    from src.infrastructure.cli import arch_repair_upgrade

    seen: list[list[str]] = []
    monkeypatch.setattr(arch_repair_upgrade, "main_upgrade", lambda rest: (seen.append(rest), 0)[1])

    exit_code = arch_repair.main(["upgrade", "--repo-root", "/tmp/x"])

    assert exit_code == 0
    assert seen == [["--repo-root", "/tmp/x"]]


def _result_for(
    args,
    *,
    repair_exists: bool = False,
    no_staged_changes: bool = False,
):
    command = tuple(args)
    if command == ("rev-parse", "--abbrev-ref", "HEAD"):
        stdout = "main\n"
    elif "--symbolic-full-name" in command:
        stdout = "origin/main\n"
    elif command[:3] == ("show-ref", "--verify", "--quiet"):
        return SimpleNamespace(returncode=0 if repair_exists else 1, stdout="", stderr="")
    elif command == ("diff", "--cached", "--quiet"):
        return SimpleNamespace(returncode=0 if no_staged_changes else 1, stdout="", stderr="")
    else:
        stdout = ""
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
