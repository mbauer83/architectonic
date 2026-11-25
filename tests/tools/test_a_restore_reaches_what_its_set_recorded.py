"""`--restore` reaches every target its set copied, refuses to discard later work, and leaves per-user state alone.

Found driving an `arch-update`:

- `arch-update` printed `safety  arch-repair upgrade --restore <set>`, and the upgrade guide documented
  `--workspace <path> --restore <set>`. Both restored the repositories only and reported the settings
  document and the assurance store as "no such target in this deployment" — they existed, but only a
  run naming the same `--settings` could see them. The set now records the settings document it was
  taken under, and a restore without one uses it.
- A restore silently discarded a stress analysis and two candidate architectures written after the
  upgrade. It now compares with the state the commit left and refuses until told to discard.
- The default guidance cache lives under the user's home directory and is read by every installation
  of that user. It was copied into one deployment's set and put back by its restore. It is now
  inspected and migrated but never checkpointed or restored.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.application.deployment_upgrade.ports import OperationalStepRegistry
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.registry import StepRegistry
from src.domain.repository.operational_upgrade import CheckpointSet
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding
from src.infrastructure.cli import arch_repair_upgrade as cli
from src.infrastructure.cli._upgrade_checkpoints import list_checkpoint_sets


class _RenameStep:
    id = "fixture-rename"
    version = 1
    description = "fixture"
    scanned_surface = "entity_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        if view.read_text("legacy.txt") is None or view.read_text("current.txt") is not None:
            return []
        return [UpgradeFinding(
            step_id=self.id, finding_id="legacy-marker", location="legacy.txt",
            description="rename legacy.txt", severity="warning", auto_migratable=True,
            rewrite_summary="legacy.txt -> current.txt",
        )]

    def apply(
        self, view: RepoUpgradeView, writer: RepoUpgradeWriter, findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        writer.write_text("current.txt", view.read_text("legacy.txt") or "")
        return [AppliedFinding(finding=f, outcome="applied") for f in findings]


def _registry() -> StepRegistry:
    registry = StepRegistry()
    registry.register(_RenameStep())
    return registry


def _run(*argv: str) -> int:
    return cli.main_upgrade(list(argv), registry=_registry(), operational_registry=OperationalStepRegistry())


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(command, cwd=path, check=True)
    (path / "legacy.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def _settings(tmp_path: Path, port: int) -> str:
    # The assurance store's default location is the source checkout's own; a checkout that holds a real,
    # locked store would make the upgrade refuse to proceed without its key. State one under tmp_path.
    store = tmp_path / "assurance" / "assurance.db"
    return f"backend:\n  port: {port}\ndeployment:\n  assurance_db_path: {store}\n"


def _only_set(base: Path) -> CheckpointSet:
    sets = list_checkpoint_sets(base)
    assert len(sets) == 1
    return sets[0]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ARCH_SETTINGS_PATH", raising=False)


def test_work_written_after_the_upgrade_stops_the_restore_until_it_is_discarded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path / "repo")
    assert _run("--repo-root", str(repo), "--commit") == 0
    checkpoint_set = _only_set(tmp_path / ".arch" / "upgrade-checkpoints")
    (repo / "analysis.md").write_text("written after the upgrade\n", encoding="utf-8")
    capsys.readouterr()

    refused = _run("--repo-root", str(repo), "--restore", checkpoint_set.id)

    assert refused == cli.EXIT_UNRESOLVED_MIGRATION
    assert "analysis.md" in capsys.readouterr().err
    assert (repo / "analysis.md").exists() and (repo / "current.txt").exists()

    assert _run("--repo-root", str(repo), "--restore", checkpoint_set.id, "--discard-later-work") == 0
    assert not (repo / "analysis.md").exists()
    assert not (repo / "current.txt").exists()


def test_a_restore_with_nothing_done_since_needs_no_confirmation(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    assert _run("--repo-root", str(repo), "--commit") == 0
    checkpoint_set = _only_set(tmp_path / ".arch" / "upgrade-checkpoints")

    assert _run("--repo-root", str(repo), "--restore", checkpoint_set.id) == 0
    assert not (repo / "current.txt").exists()


def test_a_restore_without_settings_reaches_the_settings_document_the_set_copied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path / "repo")
    settings = tmp_path / "settings.yaml"
    settings.write_text(_settings(tmp_path, 8123), encoding="utf-8")
    assert _run("--repo-root", str(repo), "--settings", str(settings), "--commit") == 0
    checkpoint_set = _only_set(tmp_path / ".arch" / "upgrade-checkpoints")
    assert checkpoint_set.settings_document == str(settings)
    assert [backup.kind for backup in checkpoint_set.operational] == ["deployment_settings"]
    settings.write_text(_settings(tmp_path, 9999), encoding="utf-8")
    capsys.readouterr()

    code = _run("--repo-root", str(repo), "--restore", checkpoint_set.id, "--discard-later-work")

    out = capsys.readouterr().out
    assert code == 0
    assert "not restored" not in out, out
    assert settings.read_text(encoding="utf-8") == _settings(tmp_path, 8123)


def test_the_per_user_guidance_cache_is_migrated_but_never_checkpointed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    from src.domain.deployment.layout import CliSelectors
    from src.infrastructure.deployment.discovery import discover_operational_handles
    from src.infrastructure.deployment.layout import resolve_manifest

    cache = tmp_path / "home" / ".config" / "arch-repo" / "guidance-cache"
    cache.mkdir(parents=True)
    (cache / "archimate-4.guidance.yaml").write_text("{}\n", encoding="utf-8")
    settings = tmp_path / "settings.yaml"
    settings.write_text(_settings(tmp_path, 8123), encoding="utf-8")

    handles = discover_operational_handles(resolve_manifest(CliSelectors(settings=str(settings))))
    guidance = [h for h in handles if h.target.kind == "guidance_cache"]
    assert guidance and guidance[0].target.per_user

    repo = _repo(tmp_path / "repo")
    assert _run("--repo-root", str(repo), "--settings", str(settings), "--commit") == 0
    checkpoint_set = _only_set(tmp_path / ".arch" / "upgrade-checkpoints")
    assert "guidance_cache" not in [backup.kind for backup in checkpoint_set.operational]
    assert "shared by every installation of this user" in capsys.readouterr().err


def test_a_deployment_with_its_own_guidance_cache_reads_and_checkpoints_that_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domain.deployment.layout import CliSelectors
    from src.infrastructure.deployment.discovery import discover_operational_handles
    from src.infrastructure.deployment.layout import resolve_manifest
    from src.infrastructure.guidance_cache import guidance_cache_root

    own = tmp_path / "deployment" / "guidance-cache"
    own.mkdir(parents=True)
    (own / "archimate-4.guidance.yaml").write_text("{}\n", encoding="utf-8")
    settings = tmp_path / "settings.yaml"
    settings.write_text(f"deployment:\n  guidance_cache_root: {own}\n", encoding="utf-8")

    handles = discover_operational_handles(resolve_manifest(CliSelectors(settings=str(settings))))
    guidance = [h for h in handles if h.target.kind == "guidance_cache"]
    assert guidance and not guidance[0].target.per_user
    assert Path(guidance[0].target.display_location) == own

    monkeypatch.setenv("ARCH_SETTINGS_PATH", str(settings))
    assert guidance_cache_root() == own


def test_a_database_is_named_before_it_is_put_back_rather_than_compared(tmp_path: Path) -> None:
    # A backend rewrites its store's file on every start (a write-ahead-log checkpoint), so a digest
    # would report "changed since the upgrade" after any restart. The store is named instead.
    from src.domain.repository.operational_upgrade import OperationalBackup
    from src.infrastructure.cli._upgrade_checkpoints import databases_restored_whole, record_state_after

    store, settings = tmp_path / "store.db", tmp_path / "settings.yaml"
    store.write_bytes(b"sqlite")
    settings.write_text("backend: {}\n", encoding="utf-8")
    base = tmp_path / "sets"
    (base / "S1").mkdir(parents=True)
    recorded = record_state_after(CheckpointSet(id="S1", operational=(
        OperationalBackup(kind="assurance_sqlcipher", location=str(store), backup_path=str(store)),
        OperationalBackup(kind="deployment_settings", location=str(settings), backup_path=str(settings)),
    )), base)

    digests = {backup.kind: backup.after_digest for backup in recorded.operational}
    assert digests["assurance_sqlcipher"] is None and digests["deployment_settings"] is not None
    assert databases_restored_whole(recorded) == [f"assurance_sqlcipher {store}"]
