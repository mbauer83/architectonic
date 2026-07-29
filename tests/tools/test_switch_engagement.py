from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from src.infrastructure.workspace import switch_engagement
from src.infrastructure.workspace.engagement_repo_template import (
    INITIAL_COMMIT_MESSAGE,
    create_engagement_repo,
)
from src.infrastructure.workspace.workspace_init import load_init_state


def _minimal_repo(path: Path) -> Path:
    (path / "model").mkdir(parents=True)
    return path


def test_switches_to_existing_configured_engagement(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _minimal_repo(workspace_root / "eng-a")
    eng_b = _minimal_repo(workspace_root / "eng-b")
    ent = _minimal_repo(workspace_root / "enterprise")
    config_path = workspace_root / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagements": {
                    "active": "eng-a",
                    "available": {
                        "eng-a": {"local": "eng-a"},
                        "eng-b": {"local": "eng-b"},
                    },
                },
                "enterprise": {"local": "enterprise"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    switch_engagement.main(["eng-b", "--config", str(config_path), "--no-restart-backend"])

    updated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert updated["engagements"]["active"] == "eng-b"
    # Catalog form is the single source of truth — no redundant top-level 'engagement'.
    assert "engagement" not in updated
    state = load_init_state(workspace_root)
    assert state is not None
    assert state["engagement_root"] == str(eng_b.resolve())
    assert state["enterprise_root"] == str(ent.resolve())


def test_switch_registers_git_engagement_and_restarts_backend(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    current = _minimal_repo(workspace_root / "eng-a")
    ent = _minimal_repo(workspace_root / "enterprise")
    config_path = workspace_root / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagement": {"local": "eng-a"},
                "enterprise": {"local": "enterprise"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    restart_calls: list[tuple[str, object]] = []

    def fake_resolve_repo(
        label: str,
        spec: dict,
        root: Path,
        *,
        allow_dirty_git_repo: bool = False,
        allow_dirty_uncommitted_git_repo: bool = False,
    ) -> Path:
        if label == "enterprise":
            return ent.resolve()
        if "local" in spec:
            return current.resolve()
        git_path = root / spec["git"]["path"]
        _minimal_repo(git_path)
        return git_path.resolve()

    monkeypatch.setattr(switch_engagement, "_resolve_repo", fake_resolve_repo)
    monkeypatch.setattr(switch_engagement, "resolve_backend_port", lambda start=None: 8123)
    monkeypatch.setattr(
        switch_engagement,
        "backend_status",
        lambda cwd=None, port=None: {"running": True, "reason": "ok", "port": port},
    )
    monkeypatch.setattr(
        switch_engagement,
        "stop_backend",
        lambda cwd=None, port=None, timeout_s=5.0: (
            restart_calls.append(("stop", port)),
            {"stopped": True, "port": port},
        )[-1],
    )
    monkeypatch.setattr(
        switch_engagement,
        "ensure_backend_running",
        lambda port=None, cwd=None, project_dir=None, start_if_missing=True: (
            restart_calls.append(("start", port)),
            int(port or 0),
        )[-1],
    )

    switch_engagement.main(
        [
            "client-b",
            "--config",
            str(config_path),
            "--url",
            "git@example.com:org/client-b.git",
        ]
    )

    updated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert updated["engagements"]["active"] == "client-b"
    assert updated["engagements"]["available"]["eng-a"]["local"] == "eng-a"
    git_spec = updated["engagements"]["available"]["client-b"]["git"]
    assert git_spec["url"] == "git@example.com:org/client-b.git"
    assert git_spec["branch"] == "main"
    assert git_spec["path"] == "client-b"
    assert restart_calls == [("stop", 8123), ("start", 8123)]


def test_switch_uses_configured_default_branch_for_new_git_engagement(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _minimal_repo(workspace_root / "eng-a")
    _minimal_repo(workspace_root / "enterprise")
    config_path = workspace_root / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagement": {"local": "eng-a"},
                "enterprise": {"local": "enterprise"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(switch_engagement, "repo_init_default_branch", lambda repo_kind=None: "trunk")
    monkeypatch.setattr(
        switch_engagement,
        "_resolve_repo",
        lambda label, spec, root, **kwargs: (root / spec["local"]).resolve()
        if "local" in spec
        else (root / spec["git"]["path"]).resolve(),
    )

    switch_engagement.main(
        [
            "client-b",
            "--config",
            str(config_path),
            "--url",
            "git@example.com:org/client-b.git",
            "--no-restart-backend",
        ]
    )

    updated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    git_spec = updated["engagements"]["available"]["client-b"]["git"]
    assert git_spec["branch"] == "trunk"


def test_switch_defaults_new_git_engagement_to_sibling_of_current_engagement(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _minimal_repo(workspace_root / "engagements" / "ENG-ARCH-REPO" / "architecture-repository")
    _minimal_repo(workspace_root / "enterprise")
    config_path = workspace_root / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagement": {"local": "engagements/ENG-ARCH-REPO/architecture-repository"},
                "enterprise": {"local": "enterprise"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        switch_engagement,
        "_resolve_repo",
        lambda label, spec, root, **kwargs: (root / spec["local"]).resolve()
        if "local" in spec
        else (root / spec["git"]["path"]).resolve(),
    )

    switch_engagement.main(
        [
            "EXAMPLE-PLATFORM",
            "--config",
            str(config_path),
            "--url",
            "git@example.com:org/example-platform.git",
            "--no-restart-backend",
        ]
    )

    updated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    git_spec = updated["engagements"]["available"]["EXAMPLE-PLATFORM"]["git"]
    assert git_spec["path"] == "engagements/EXAMPLE-PLATFORM/architecture-repository"


def test_switch_repairs_stale_existing_git_path_to_canonical_engagement_location(
    monkeypatch, tmp_path: Path
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _minimal_repo(workspace_root / "engagements" / "ENG-ARCH-REPO" / "architecture-repository")
    repaired_repo = _minimal_repo(
        workspace_root / "engagements" / "EXAMPLE-PLATFORM" / "architecture-repository"
    )
    _minimal_repo(workspace_root / "enterprise")
    config_path = workspace_root / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagement": {
                    "git": {
                        "url": "git@example.com:org/example-platform.git",
                        "branch": "main",
                        "path": "../EXAMPLE-PLATFORM",
                    }
                },
                "enterprise": {"local": "enterprise"},
                "engagements": {
                    "active": "EXAMPLE-PLATFORM",
                    "available": {
                        "ENG-ARCH-REPO": {"local": "engagements/ENG-ARCH-REPO/architecture-repository"},
                        "EXAMPLE-PLATFORM": {
                            "git": {
                                "url": "git@example.com:org/example-platform.git",
                                "branch": "main",
                                "path": "../EXAMPLE-PLATFORM",
                            }
                        },
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        switch_engagement,
        "_resolve_repo",
        lambda label, spec, root, **kwargs: (root / spec["local"]).resolve()
        if "local" in spec
        else (root / spec["git"]["path"]).resolve(),
    )

    switch_engagement.main(["EXAMPLE-PLATFORM", "--config", str(config_path), "--no-restart-backend"])

    updated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    git_spec = updated["engagements"]["available"]["EXAMPLE-PLATFORM"]["git"]
    assert git_spec["path"] == "engagements/EXAMPLE-PLATFORM/architecture-repository"
    state = load_init_state(workspace_root)
    assert state is not None
    assert state["engagement_root"] == str(repaired_repo.resolve())


def test_switch_can_create_new_local_engagement_repo(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _minimal_repo(workspace_root / "eng-a")
    _minimal_repo(workspace_root / "enterprise")
    config_path = workspace_root / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagement": {"local": "eng-a"},
                "enterprise": {"local": "enterprise"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    switch_engagement.main(
        [
            "eng-b",
            "--config",
            str(config_path),
            "--local",
            "eng-b",
            "--create",
            "--no-restart-backend",
        ]
    )

    eng_b = workspace_root / "eng-b"
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=eng_b,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=eng_b,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert (eng_b / "model").is_dir()
    assert (eng_b / ".git").is_dir()
    assert (eng_b / "diagram-catalog" / "diagrams").is_dir()
    assert (eng_b / ".arch-repo" / "documents" / "adr.json").is_file()
    assert (eng_b / ".arch-repo" / "schemata" / "frontmatter.entity.schema.json").is_file()
    assert head.returncode == 0
    assert head.stdout.strip() == "main"
    assert commit.returncode == 0
    state = load_init_state(workspace_root)
    assert state is not None
    assert state["engagement_root"] == str(eng_b.resolve())


def test_switch_ignores_dirty_enterprise_repo(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    _minimal_repo(workspace_root / "eng-a")
    config_path = workspace_root / "arch-workspace.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "engagement": {"local": "eng-a"},
                "enterprise": {
                    "git": {
                        "url": "git@example.com:org/enterprise.git",
                        "branch": "main",
                        "path": "../enterprise",
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    resolve_calls: list[tuple[str, bool, bool]] = []
    enterprise_root = tmp_path / "enterprise"
    enterprise_root.mkdir()
    _minimal_repo(enterprise_root)

    def fake_resolve_repo(
        label: str,
        spec: dict,
        root: Path,
        *,
        allow_dirty_git_repo: bool = False,
        allow_dirty_uncommitted_git_repo: bool = False,
    ) -> Path:
        resolve_calls.append((label, allow_dirty_git_repo, allow_dirty_uncommitted_git_repo))
        if label == "enterprise":
            return enterprise_root.resolve()
        return (root / spec["local"]).resolve()

    monkeypatch.setattr(switch_engagement, "_resolve_repo", fake_resolve_repo)

    switch_engagement.main(["eng-a", "--config", str(config_path), "--no-restart-backend"])

    assert ("enterprise", True, False) in resolve_calls


def test_create_engagement_repo_initializes_git_remote(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "eng-git"
    commands: list[list[str]] = []

    def fake_run(command, cwd=None, capture_output=None, text=None, timeout=None):
        commands.append(command)

        class Result:
            def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        if command[:4] == ["git", "remote", "get-url", "origin"]:
            return Result(1, stderr="missing")
        if command[:3] == ["git", "init", "-b"]:
            (repo_root / ".git").mkdir(parents=True, exist_ok=True)
        if command[:4] == ["git", "rev-parse", "--verify", "HEAD"]:
            return Result(1, stderr="unknown revision")
        return Result(0)

    monkeypatch.setattr("src.infrastructure.workspace.engagement_repo_template.subprocess.run", fake_run)

    create_engagement_repo(
        repo_root,
        git_url="git@example.com:org/eng-git.git",
        branch="trunk",
        commit_author_name="Architecture Bot",
        commit_author_email="architecture-bot@example.com",
    )

    assert (repo_root / ".git").is_dir()
    assert (repo_root / ".arch-repo" / "documents" / "standard.json").is_file()
    assert ["git", "init", "-b", "trunk"] in commands
    assert ["git", "add", "-A"] in commands
    assert ["git", "remote", "add", "origin", "git@example.com:org/eng-git.git"] in commands
    assert [
        "git",
        "-c",
        "user.name=Architecture Bot",
        "-c",
        "user.email=architecture-bot@example.com",
        "commit",
        "-m",
        INITIAL_COMMIT_MESSAGE,
    ] in commands
