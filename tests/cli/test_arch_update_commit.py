"""`--commit` journals, hands over by re-executing, resumes as the new version, and rolls back on failure."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.application.software_update.evaluate import ReleaseCheck
from src.application.software_update.installation import (
    BackendObservation,
    DependencySelection,
    InstallationObservation,
    InstalledSoftware,
    StoreObservation,
    Tooling,
)
from src.application.software_update.plan import ReleaseVerification, UpdatePlan, UpdateStep
from src.application.software_update.ports import MigrationIncomplete, MigrationResult
from src.application.software_update.release import PublishedRelease, ReleaseAsset, sha256_of
from src.application.software_update.version import ReleaseVersion
from src.infrastructure.cli import _update_commit
from src.infrastructure.software_update.journal_store import FileJournalStore

BUNDLE = b"gui bundle bytes"
RELEASE = PublishedRelease(
    ReleaseVersion(0, 10, 1), "v0.10.1", "def4567abc", "2026-10-02T09:00:00Z", False,
    (ReleaseAsset("architectonic-gui-0.10.1.tar.gz", "https://x/gui", sha256_of(BUNDLE), len(BUNDLE)),),
)
INSTALLED = InstalledSoftware(ReleaseVersion(0, 10, 0), "abc1234def", "main", (), True, "stamp", "1.2026.3")


@dataclass
class FakeActions:
    fail_at: str | None = None
    calls: list[str] = field(default_factory=list)

    def _note(self, name: str) -> None:
        self.calls.append(name)
        if name == self.fail_at:
            self.fail_at = None  # the rollback's own call of the same action succeeds
            raise RuntimeError(f"{name} broke")

    def stop_backend(self, port):  # noqa: ANN001, ANN201
        self._note("stop_backend")

    def start_backend(self, previous):  # noqa: ANN001, ANN201
        self._note("start_backend")

    def move_checkout(self, tag, move):  # noqa: ANN001, ANN201
        self._note("move_checkout")

    def restore_checkout(self, commit, branch):  # noqa: ANN001, ANN201
        self._note("restore_checkout")

    def sync_environment(self, selection):  # noqa: ANN001, ANN201
        self._note("sync_environment")

    def install_gui(self, gui, target):  # noqa: ANN001, ANN201
        self._note("install_gui")

    def restore_gui(self):  # noqa: ANN201
        self._note("restore_gui")

    def reconcile_assets(self):  # noqa: ANN201
        self._note("reconcile_assets")
        return ()

    def migrate(self):  # noqa: ANN201
        if self.fail_at == "migrate_partially":
            self.calls.append("migrate")
            raise MigrationIncomplete("exit 20", checkpoint_set="20261002T090100Z")
        self._note("migrate")
        return MigrationResult("20261002T090100Z", True)

    def restore_checkpoint(self, checkpoint_set):  # noqa: ANN001, ANN201
        self._note(f"restore_checkpoint:{checkpoint_set}")

    def authorize_store(self):  # noqa: ANN201
        self._note("authorize_store")

    def verify(self, target, *, backend_expected):  # noqa: ANN001, ANN201
        self._note("verify")


def _check() -> ReleaseCheck:
    verification = ReleaseVerification(True, "verified", (), "not_verified", "gh not on PATH")
    return ReleaseCheck(INSTALLED, RELEASE, RELEASE.commit, verification, {RELEASE.gui_bundle_name: BUNDLE})


def _observation(*, running: bool = True) -> InstallationObservation:
    return InstallationObservation(
        kind="local-checkout", software=INSTALLED, selection=DependencySelection(("gui",), ()),
        backend=BackendObservation(running, 4242 if running else None, 8000 if running else None, True, ()),
        store=StoreObservation(True, running, "manual", True),
        remotes_needing_credentials=(), tooling=Tooling(True, True, False, False), interactive=False,
    )


def _plan() -> UpdatePlan:
    return UpdatePlan(
        ReleaseVersion(0, 10, 1), "fast_forward", "from_release", (UpdateStep("verify", "verify"),), (), (),
        restart_backend=True, authorize_store=True,
    )


def _commit(root: Path, *, json_output: bool = True) -> int:
    return _update_commit.commit(
        _check(), _observation(), _plan(), root=root, json_output=json_output, resolve_selection=(),
    )


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):  # noqa: ANN201
    """The actions and the exec are fakes; the journal store, the lock and the assets are real files."""
    execs: list[list[str]] = []

    def wire(actions: FakeActions) -> list[list[str]]:
        monkeypatch.setattr(_update_commit, "LocalCheckoutActions", lambda *a, **k: actions)
        monkeypatch.setattr(_update_commit, "deployment_identity_arguments", lambda root: ("--workspace", str(root)))
        monkeypatch.setattr(_update_commit, "answer_questions", lambda *a, **k: ())
        monkeypatch.setattr(_update_commit.os, "execv", lambda executable, argv: execs.append(list(argv)))
        return execs

    return wire


def test_commit_runs_to_the_handover_persists_the_bundle_and_re_executes_as_the_new_version(
    wired, tmp_path: Path, capsys,  # noqa: ANN001
) -> None:
    actions = FakeActions()
    execs = wired(actions)

    with pytest.raises(AssertionError, match="execv returned"):
        _commit(tmp_path)

    assert actions.calls == ["stop_backend", "move_checkout", "sync_environment"]
    assert execs[0][-3:] == ["arch-update", "--resume", "--json"] and "--project" in execs[0]
    store = FileJournalStore(tmp_path)
    journal = store.read()
    assert journal is not None and journal.handed_over and journal.target.gui_bundle_sha256 == sha256_of(BUNDLE)
    assert (store.directory / "assets" / RELEASE.gui_bundle_name).read_bytes() == BUNDLE
    assert not store.lock_path.exists(), "the lock is handed over by release, not by pid"
    assert execs[0][1:4] == ["run", "--frozen", "--no-sync"]


def test_resume_completes_the_update_archives_it_and_exits_zero(wired, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    wired(FakeActions())
    with pytest.raises(AssertionError):
        _commit(tmp_path)
    actions = FakeActions()
    wired(actions)
    capsys.readouterr()

    assert _update_commit.resume(tmp_path, json_output=True) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["outcome"] == "updated" and report["checkpoint_set"] == "20261002T090100Z"
    assert actions.calls == ["install_gui", "reconcile_assets", "migrate", "start_backend", "authorize_store", "verify"]
    store = FileJournalStore(tmp_path)
    assert store.read() is None and store.last_archived()["outcome"] == "updated"
    assert not (store.directory / "assets").exists() and not store.lock_path.exists()


def test_a_failure_after_the_handover_rolls_back_and_exits_blocked(wired, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    wired(FakeActions())
    with pytest.raises(AssertionError):
        _commit(tmp_path, json_output=False)
    actions = FakeActions(fail_at="verify")
    wired(actions)
    capsys.readouterr()

    assert _update_commit.resume(tmp_path, json_output=False) == 3

    out = capsys.readouterr().out
    assert out.startswith("blocked") and "restore_checkpoint:20261002T090100Z" in actions.calls
    assert not (FileJournalStore(tmp_path).directory / "assets").exists(), "a rollback leaves no bundle behind"
    assert "restore_checkout" in actions.calls and actions.calls[-2:] == ["start_backend", "authorize_store"]
    assert FileJournalStore(tmp_path).last_archived()["outcome"] == "blocked"


def test_a_partial_migration_records_its_checkpoint_before_the_rollback_restores_it(
    wired, tmp_path: Path, capsys,  # noqa: ANN001
) -> None:
    wired(FakeActions())
    with pytest.raises(AssertionError):
        _commit(tmp_path)
    actions = FakeActions(fail_at="migrate_partially")
    wired(actions)
    capsys.readouterr()

    assert _update_commit.resume(tmp_path, json_output=True) == 3

    report = json.loads(capsys.readouterr().out)
    assert report["checkpoint_set"] == "20261002T090100Z" and "restore_checkpoint:20261002T090100Z" in actions.calls


def test_a_failure_before_the_handover_rolls_back_in_the_same_process(wired, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    actions = FakeActions(fail_at="sync_environment")
    wired(actions)

    code = _commit(tmp_path)

    assert code == 3
    assert actions.calls == [
        "stop_backend", "move_checkout", "sync_environment",
        "restore_checkout", "sync_environment", "start_backend", "authorize_store",
    ]
    report = json.loads(capsys.readouterr().out)
    assert report["outcome"] == "blocked" and report["failure"].startswith("environment_synced")


def test_resume_and_rollback_without_a_journal_are_usage_errors(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    assert _update_commit.resume(tmp_path, json_output=False) == 2
    assert _update_commit.rollback(tmp_path, json_output=False) == 2
    assert _update_commit.status(tmp_path, json_output=False) == 0
    assert "no update in flight" in capsys.readouterr().out


def test_a_second_commit_while_one_is_in_flight_is_refused(wired, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    wired(FakeActions())
    with pytest.raises(AssertionError):
        _commit(tmp_path)

    code = _commit(tmp_path)

    assert code == 21 and "already in flight" in capsys.readouterr().err
    assert _update_commit.status(tmp_path, json_output=False) == 0
    assert "handed over" in capsys.readouterr().out
