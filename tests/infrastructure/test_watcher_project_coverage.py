from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.infrastructure.mcp.artifact_mcp import watch_tools


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_project_model_change_is_present_in_incremental_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    project_file = (
        repo
        / "projects"
        / "payments"
        / "model"
        / "application"
        / "application-component"
        / "APP@1712870400.Abc123.payments.md"
    )
    _write(project_file, "before")
    before = watch_tools._repo_state_snapshot(repo)

    _write(project_file, "after-with-a-different-size")
    after = watch_tools._repo_state_snapshot(repo)
    changed, full_refresh = watch_tools._diff_snapshots(
        {repo.resolve(): before},
        {repo.resolve(): after},
    )

    assert changed == [project_file]
    assert full_refresh is False


def test_watcher_enqueues_project_change_while_holding_mutation_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    project_file = repo / "projects" / "payments" / "model" / "motivation" / "goal" / "GOL@test.md"
    snapshots = iter(
        [
            {repo.resolve(): {}},
            {repo.resolve(): {project_file.relative_to(repo).as_posix(): (1, 1)}},
        ]
    )
    stop = threading.Event()
    gate = _RecordingGate()
    calls: list[tuple[list[Path], list[Path] | None, bool, bool]] = []

    monkeypatch.setattr(watch_tools, "_roots_state_snapshot", lambda _roots: next(snapshots))
    monkeypatch.setattr(watch_tools, "get_workspace_gate", lambda: gate)
    monkeypatch.setattr(watch_tools.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        watch_tools,
        "enqueue_background_refresh",
        lambda roots, *, changed_paths=None, full_refresh: (
            calls.append((roots, changed_paths, full_refresh, gate.held)),
            stop.set(),
        ),
    )

    watch_tools._watcher_loop([repo], 2.0, stop)

    assert calls == [([repo], [project_file], False, True)]


class _RecordingGate:
    def __init__(self) -> None:
        self.held = False

    @contextmanager
    def writing(self) -> Iterator[None]:
        self.held = True
        try:
            yield
        finally:
            self.held = False
