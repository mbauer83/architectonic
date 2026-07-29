"""Regression: auto-initialize an existing git clone that lacks the arch-repo structure.

Reproduces the docker-compose startup failure where a freshly-created remote (cloned with
only a README onto branch ``main``) was reported as "existing clone OK" and then rejected
with "cloned engagement repo has no model/ directory", looping forever. With
``initialize_if_empty`` the structure must instead be scaffolded into the clone in place.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.config.repo_paths import ARCH_REPO, MODEL
from src.infrastructure.workspace import workspace_init
from src.infrastructure.workspace.engagement_repo_template import initialize_arch_repo_in_place
from src.infrastructure.workspace.workspace_init import _resolve_repo


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@local.invalid", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    )


def _clone_with_readme(path: Path) -> Path:
    """A git checkout on main with one commit (README) but no arch-repo structure."""
    path.mkdir(parents=True)
    _git(["init", "-b", "main"], path)
    (path / "README.md").write_text("# Engagement\n", encoding="utf-8")
    _git(["add", "-A"], path)
    _git(["commit", "-m", "initial readme"], path)
    return path


def _readme_remote(tmp_path: Path, name: str) -> Path:
    """A bare remote whose ``main`` has a README but no arch-repo structure."""
    remote = tmp_path / name
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True, text=True)
    seed = _clone_with_readme(tmp_path / f"{name}-seed")
    _git(["remote", "add", "origin", str(remote)], seed)
    _git(["push", "origin", "main"], seed)
    return remote


def _head(path: Path, ref: str = "HEAD") -> str:
    return subprocess.run(["git", "rev-parse", ref], cwd=path, capture_output=True, text=True).stdout.strip()


def _is_clean(path: Path) -> bool:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True)
    return not out.stdout.strip()


def _commit_count(path: Path) -> int:
    out = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=path, capture_output=True, text=True)
    return int(out.stdout.strip())


class TestInitializeArchRepoInPlace:
    def test_scaffolds_structure_into_existing_clone(self, tmp_path: Path) -> None:
        repo = _clone_with_readme(tmp_path / "eng")

        initialize_arch_repo_in_place(repo)

        assert (repo / MODEL).is_dir()
        assert (repo / ARCH_REPO).is_dir()
        assert (repo / "README.md").exists()  # pre-existing content is preserved

    def test_commits_the_scaffold_on_top_of_existing_history(self, tmp_path: Path) -> None:
        repo = _clone_with_readme(tmp_path / "eng")

        initialize_arch_repo_in_place(repo)

        assert _is_clean(repo), "scaffold must be committed, leaving a clean tree"
        assert _commit_count(repo) == 2  # readme + scaffold

    def test_idempotent_second_call_is_noop(self, tmp_path: Path) -> None:
        repo = _clone_with_readme(tmp_path / "eng")
        initialize_arch_repo_in_place(repo)

        initialize_arch_repo_in_place(repo)

        assert _commit_count(repo) == 2
        assert _is_clean(repo)


class TestResolveRepoAutoInit:
    def test_clone_without_model_is_scaffolded_and_published_when_flag_set(self, tmp_path: Path) -> None:
        remote = _readme_remote(tmp_path, "eng.git")
        ws = tmp_path / "ws"
        ws.mkdir()
        dest = ws / "eng"
        subprocess.run(["git", "clone", str(remote), str(dest)], check=True, capture_output=True, text=True)
        spec = {"git": {"url": str(remote), "branch": "main", "path": "eng"}}

        result = _resolve_repo("engagement", spec, ws, initialize_if_empty=True)

        assert result == dest.resolve()
        assert (dest / MODEL).is_dir()
        # The scaffold is published, not left as an unsynchronized local commit.
        assert _is_clean(dest)
        assert _head(remote, "main") == _head(dest)

    def test_clone_without_model_still_raises_without_flag(self, tmp_path: Path) -> None:
        remote = _readme_remote(tmp_path, "eng.git")
        ws = tmp_path / "ws"
        ws.mkdir()
        dest = ws / "eng"
        subprocess.run(["git", "clone", str(remote), str(dest)], check=True, capture_output=True, text=True)
        spec = {"git": {"url": str(remote), "branch": "main", "path": "eng"}}

        with pytest.raises(SystemExit, match="no model content"):
            _resolve_repo("engagement", spec, ws, initialize_if_empty=False)


class TestArchInitMainWiring:
    """End-to-end: the --initialize-*-if-empty CLI flags reach _resolve_repo, scaffold, and publish.

    This is the exact docker entrypoint path (arch-init --initialize-engagement-repo-if-empty
    --initialize-enterprise-repo-if-empty) that the container runs on first boot against
    brand-new remotes that contain only a README.
    """

    def test_main_scaffolds_and_publishes_readme_clones(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        eng_remote = _readme_remote(tmp_path, "eng.git")
        ent_remote = _readme_remote(tmp_path, "ent.git")
        ws = tmp_path / "ws"
        ws.mkdir()
        for remote, name in ((eng_remote, "engagement"), (ent_remote, "enterprise")):
            subprocess.run(
                ["git", "clone", str(remote), str(ws / "data" / name)], check=True, capture_output=True, text=True
            )
        config = ws / "arch-workspace.yaml"
        config.write_text(
            f"engagement:\n"
            f"  git: {{ url: '{eng_remote}', branch: main, path: data/engagement }}\n"
            f"enterprise:\n"
            f"  git: {{ url: '{ent_remote}', branch: main, path: data/enterprise }}\n",
            encoding="utf-8",
        )
        # Dests already exist locally — no cloning or credentials needed.
        monkeypatch.setattr(workspace_init, "_collect_init_credentials", lambda _cfg: None)

        workspace_init.main([
            "--config", str(config),
            "--initialize-engagement-repo-if-empty",
            "--initialize-enterprise-repo-if-empty",
        ])

        assert (ws / "data" / "engagement" / MODEL).is_dir()
        assert (ws / "data" / "enterprise" / MODEL).is_dir()
        assert _head(eng_remote, "main") == _head(ws / "data" / "engagement")
        assert _head(ent_remote, "main") == _head(ws / "data" / "enterprise")
        assert workspace_init.load_init_state(ws) is not None
