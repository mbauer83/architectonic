"""Tests for workspace_init: config parsing, state file, load_init_state."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.workspace import git_remote, workspace_init
from src.infrastructure.workspace.workspace_init import (
    _current_branch,
    _parse_config,
    _resolve_repo,
    _write_state,
    load_init_state,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


def _minimal_repo(path: Path) -> Path:
    (path / "model").mkdir(parents=True)
    return path


class TestParseConfig:
    def test_valid_local_config(self, tmp_path: Path) -> None:
        cfg = {"engagement": {"local": "eng"}, "enterprise": {"local": "ent"}}
        import yaml

        f = tmp_path / "arch-workspace.yaml"
        f.write_text(yaml.safe_dump(cfg))
        result = _parse_config(f)
        assert result["engagement"]["local"] == "eng"

    def test_missing_enterprise_key_raises(self, tmp_path: Path) -> None:
        import yaml

        f = tmp_path / "arch-workspace.yaml"
        f.write_text(yaml.safe_dump({"engagement": {"local": "eng"}}))
        with pytest.raises(SystemExit, match="enterprise"):
            _parse_config(f)

    def test_missing_engagement_key_raises(self, tmp_path: Path) -> None:
        import yaml

        f = tmp_path / "arch-workspace.yaml"
        f.write_text(yaml.safe_dump({"enterprise": {"local": "ent"}}))
        with pytest.raises(SystemExit, match="engagement"):
            _parse_config(f)

    def test_engagement_catalog_selects_active_entry(self, tmp_path: Path) -> None:
        import yaml

        f = tmp_path / "arch-workspace.yaml"
        f.write_text(
            yaml.safe_dump(
                {
                    "engagements": {
                        "active": "eng-b",
                        "available": {
                            "eng-a": {"local": "eng-a"},
                            "eng-b": {"local": "eng-b"},
                        },
                    },
                    "enterprise": {"local": "ent"},
                }
            )
        )
        result = _parse_config(f)
        assert result["engagement"]["local"] == "eng-b"

    def test_conflicting_top_level_engagement_and_catalog_raises(self, tmp_path: Path) -> None:
        import yaml

        f = tmp_path / "arch-workspace.yaml"
        f.write_text(
            yaml.safe_dump(
                {
                    "engagement": {"local": "eng-a"},
                    "engagements": {
                        "active": "eng-b",
                        "available": {
                            "eng-a": {"local": "eng-a"},
                            "eng-b": {"local": "eng-b"},
                        },
                    },
                    "enterprise": {"local": "ent"},
                }
            )
        )
        with pytest.raises(SystemExit, match="conflicts"):
            _parse_config(f)


class TestResolveRepo:
    def test_local_path_resolved(self, tmp_path: Path) -> None:
        repo = _minimal_repo(tmp_path / "my-repo")
        result = _resolve_repo("test", {"local": str(repo)}, tmp_path)
        assert result == repo.resolve()

    def test_local_relative_path(self, tmp_path: Path) -> None:
        repo = _minimal_repo(tmp_path / "relative-repo")
        result = _resolve_repo("test", {"local": "relative-repo"}, tmp_path)
        assert result == repo.resolve()

    def test_nonexistent_local_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="does not exist"):
            _resolve_repo("test", {"local": "ghost"}, tmp_path)

    def test_local_without_model_dir_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty-repo"
        empty.mkdir()
        with pytest.raises(SystemExit, match="model"):
            _resolve_repo("test", {"local": str(empty)}, tmp_path)

    def test_local_projects_era_layout_accepted(self, tmp_path: Path) -> None:
        repo = tmp_path / "projects-repo"
        (repo / "projects" / "platform-core" / "model").mkdir(parents=True)
        result = _resolve_repo("test", {"local": str(repo)}, tmp_path)
        assert result == repo.resolve()

    def test_local_projects_dir_without_model_raises(self, tmp_path: Path) -> None:
        repo = tmp_path / "projects-no-model"
        (repo / "projects" / "platform-core").mkdir(parents=True)
        with pytest.raises(SystemExit, match="model"):
            _resolve_repo("test", {"local": str(repo)}, tmp_path)

    def test_missing_spec_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="local.*git"):
            _resolve_repo("test", {}, tmp_path)

    def test_current_branch_accepts_unborn_head(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        class Result:
            def __init__(self, returncode: int, stdout: str = "") -> None:
                self.returncode = returncode
                self.stdout = stdout

        calls: list[list[str]] = []

        def fake_run_git(args: list[str], cwd: Path | None = None) -> Result:
            calls.append(args)
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return Result(128, "")
            if args == ["symbolic-ref", "--quiet", "--short", "HEAD"]:
                return Result(0, "main\n")
            raise AssertionError(args)

        monkeypatch.setattr("src.infrastructure.workspace.workspace_init._run_git", fake_run_git)

        branch = _current_branch(tmp_path)

        assert branch == "main"
        assert calls == [
            ["rev-parse", "--abbrev-ref", "HEAD"],
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
        ]

    def test_empty_existing_checkout_delegates_to_reconcile(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A committed-less existing checkout is handed to git_remote for clone-vs-init reconciliation."""
        repo = tmp_path / "eng-git"
        repo.mkdir()
        (repo / ".git").mkdir()

        branch_state: dict[str, str | None] = {"branch": None}
        monkeypatch.setattr(workspace_init, "_current_branch", lambda path: branch_state["branch"])
        monkeypatch.setattr(workspace_init, "_has_commits", lambda path: False)

        calls: list[git_remote.BootstrapContext] = []

        def fake_reconcile(ctx: git_remote.BootstrapContext) -> None:
            calls.append(ctx)
            (ctx.dest / "model").mkdir(parents=True, exist_ok=True)
            branch_state["branch"] = ctx.branch

        monkeypatch.setattr(git_remote, "reconcile_empty_checkout", fake_reconcile)

        result = _resolve_repo(
            "engagement",
            {"git": {"url": "git@example.com:org/eng.git", "branch": "main", "path": "eng-git"}},
            tmp_path,
            initialize_if_empty=True,
        )

        assert result == repo.resolve()
        assert calls and calls[0].branch == "main"
        assert calls[0].initialize_if_empty is True

    def test_absent_dest_delegates_to_bootstrap(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """A missing clone directory is handed to git_remote.bootstrap_absent (clone or init+publish)."""
        repo = tmp_path / "ent-git"

        calls: list[git_remote.BootstrapContext] = []

        def fake_bootstrap(ctx: git_remote.BootstrapContext) -> None:
            calls.append(ctx)
            (ctx.dest / ".git").mkdir(parents=True, exist_ok=True)
            (ctx.dest / "model").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(git_remote, "bootstrap_absent", fake_bootstrap)

        result = _resolve_repo(
            "enterprise",
            {"git": {"url": "git@example.com:org/ent.git", "branch": "main", "path": "ent-git"}},
            tmp_path,
            initialize_if_empty=True,
        )

        assert result == repo.resolve()
        assert calls and calls[0].dest == repo.resolve()
        assert calls[0].initialize_if_empty is True

    def test_git_repo_without_branch_still_raises_without_initialize_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        repo = tmp_path / "eng-git"
        repo.mkdir()
        (repo / ".git").mkdir()
        monkeypatch.setattr(workspace_init, "_current_branch", lambda path: None)
        monkeypatch.setattr(workspace_init, "_has_commits", lambda path: False)
        # Remote empty + no init flag → reconcile is a no-op, so the branch stays unset.
        monkeypatch.setattr(git_remote, "reconcile_empty_checkout", lambda ctx: None)

        with pytest.raises(SystemExit, match="expected 'main'"):
            _resolve_repo(
                "engagement",
                {"git": {"url": "git@example.com:org/eng.git", "branch": "main", "path": "eng-git"}},
                tmp_path,
            )


class TestWriteAndLoadState:
    def test_write_then_load(self, tmp_path: Path) -> None:
        eng = tmp_path / "eng"
        ent = tmp_path / "ent"
        eng.mkdir()
        ent.mkdir()
        state_path = _write_state(tmp_path, eng, ent)
        assert state_path.exists()

        loaded = load_init_state(tmp_path)
        assert loaded is not None
        assert loaded["engagement_root"] == str(eng)
        assert loaded["enterprise_root"] == str(ent)

    def test_load_walks_up(self, tmp_path: Path) -> None:
        eng = tmp_path / "eng"
        ent = tmp_path / "ent"
        eng.mkdir()
        ent.mkdir()
        _write_state(tmp_path, eng, ent)

        subdir = tmp_path / "deep" / "nested"
        subdir.mkdir(parents=True)
        loaded = load_init_state(subdir)
        assert loaded is not None
        assert "engagement_root" in loaded

    def test_load_returns_none_when_not_found(self, tmp_path: Path) -> None:
        result = load_init_state(tmp_path / "no-state-here")
        assert result is None


class TestArchInitFlags:
    def test_initialize_flags_are_passed_to_repo_resolution(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import yaml

        from src.infrastructure.workspace import workspace_init

        config_path = tmp_path / "arch-workspace.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "engagement": {"git": {"url": "git@example.com:org/eng.git", "branch": "main", "path": "eng"}},
                    "enterprise": {
                        "git": {"url": "git@example.com:org/ent.git", "branch": "main", "path": "ent"}
                    },
                }
            ),
            encoding="utf-8",
        )

        calls: list[tuple[str, bool]] = []

        def fake_resolve_repo(label: str, spec: dict, workspace_root: Path, **kwargs) -> Path:
            calls.append((label, bool(kwargs.get("initialize_if_empty"))))
            resolved = workspace_root / ("eng" if label == "engagement" else "ent")
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved

        monkeypatch.setattr(workspace_init, "_resolve_repo", fake_resolve_repo)

        workspace_init.main(
            [
                "--config",
                str(config_path),
                "--initialize-engagement-repo-if-empty",
                "--initialize-enterprise-repo-if-empty",
            ]
        )

        assert ("engagement", True) in calls
        assert ("enterprise", True) in calls
        out = capsys.readouterr().out
        assert "arch-init: success" in out


# ---------------------------------------------------------------------------
# resolve_server_roots — env var / init-state priority chain
# ---------------------------------------------------------------------------


class TestResolveServerRoots:
    """Regression tests for the root resolution priority in gui_server.

    Covers the Docker use case: when --enterprise-root is not given as a CLI
    arg but ARCH_ENTERPRISE_ROOT is set in the environment, the env var must
    be used so that containers can expose both repos without requiring init-state.
    """

    def test_explicit_args_take_priority(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.infrastructure.gui.gui_server import resolve_server_roots

        eng = tmp_path / "eng-arg"
        ent = tmp_path / "ent-arg"
        monkeypatch.setenv("ARCH_REPO_ROOT", str(tmp_path / "eng-env"))
        monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", str(tmp_path / "ent-env"))
        eng_result, ent_result = resolve_server_roots(str(eng), str(ent))
        assert eng_result == eng
        assert ent_result == ent

    def test_env_vars_used_when_no_args_and_no_init_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure.gui.gui_server import resolve_server_roots

        eng = tmp_path / "eng-env"
        ent = tmp_path / "ent-env"
        monkeypatch.setenv("ARCH_REPO_ROOT", str(eng))
        monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", str(ent))
        # Redirect init-state lookup to an isolated dir with no state file
        monkeypatch.chdir(tmp_path)
        eng_result, ent_result = resolve_server_roots(None, None)
        assert eng_result == eng
        assert ent_result == ent

    def test_enterprise_env_var_used_when_only_repo_root_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mirrors the Docker scenario: --repo-root /repo set, ARCH_ENTERPRISE_ROOT=/enterprise-repo."""
        from src.infrastructure.gui.gui_server import resolve_server_roots

        ent = tmp_path / "enterprise-repo"
        monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", str(ent))
        monkeypatch.delenv("ARCH_REPO_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        eng_result, ent_result = resolve_server_roots("/repo", None)
        assert eng_result == Path("/repo")
        assert ent_result == ent

    def test_init_state_used_as_fallback_when_no_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure.gui.gui_server import resolve_server_roots

        eng = tmp_path / "eng-state"
        ent = tmp_path / "ent-state"
        _write_state(tmp_path, eng, ent)
        monkeypatch.delenv("ARCH_REPO_ROOT", raising=False)
        monkeypatch.delenv("ARCH_ENTERPRISE_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        eng_result, ent_result = resolve_server_roots(None, None)
        assert eng_result == eng
        assert ent_result == ent

    def test_returns_none_when_nothing_configured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.infrastructure.gui.gui_server import resolve_server_roots

        monkeypatch.delenv("ARCH_REPO_ROOT", raising=False)
        monkeypatch.delenv("ARCH_ENTERPRISE_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        eng_result, ent_result = resolve_server_roots(None, None)
        assert eng_result is None
        assert ent_result is None
