"""A backend that stopped records how; nothing recorded why, and twice nobody could tell.

The teardown log is complete about mechanism — every step, in order, completing — and silent about
cause, because the cause belongs to a *different process*. A stopper logs to its own stderr: a CLI
invocation that has since scrolled away, or a test's captured output that was thrown away. So a stop
request writes itself into the backend's own log, where anyone asking the question is already
reading, and the backend writes which signal it received as that signal lands.

Their absence carries meaning too, which is why the writing must be reliable in one direction only: a
drain with no stop request above it was not asked for by this project's tooling. That inference is
only sound if a stop request never silently fails to record itself when it could have — and only
safe if recording never breaks a stop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.backend import stop_provenance
from src.infrastructure.backend.stop_provenance import record_stop_request


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".arch" / "backend.log"
    monkeypatch.setattr(stop_provenance, "backend_log_path", lambda cwd: path)
    return path


def test_a_stop_request_names_the_process_that_asked(log: Path) -> None:
    """A pid alone is useless by the time anyone reads this — the process will be gone."""
    import os
    import sys

    record_stop_request(cwd=None, port=8000)
    written = log.read_text(encoding="utf-8")
    assert "STOP REQUESTED" in written
    assert f"by_pid={os.getpid()}" in written
    assert Path(sys.argv[0]).name in written or "argv=" in written


def test_it_names_the_port_so_two_workspaces_are_not_confused(log: Path) -> None:
    record_stop_request(cwd=None, port=8123)
    assert "port=8123" in log.read_text(encoding="utf-8")


def test_it_names_the_target_when_one_is_known(log: Path) -> None:
    record_stop_request(cwd=None, port=8000, target_pid=4321)
    assert "target_pid=4321" in log.read_text(encoding="utf-8")


def test_it_says_nothing_about_a_target_it_does_not_know(log: Path) -> None:
    """Better absent than invented: the stop paths differ in whether a pid is resolved yet."""
    record_stop_request(cwd=None, port=8000)
    assert "target_pid=" not in log.read_text(encoding="utf-8")


def test_each_request_is_its_own_line(log: Path) -> None:
    """Two stops in a session are two events, and a reader correlates them by time."""
    record_stop_request(cwd=None, port=8000)
    record_stop_request(cwd=None, port=8000)
    assert len([line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]) == 2


def test_it_appends_rather_than_replacing_what_the_backend_wrote(log: Path) -> None:
    """It writes into a live log the backend is also writing; truncating it would destroy the
    teardown record this exists to be read beside."""
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("earlier backend output\n", encoding="utf-8")
    record_stop_request(cwd=None, port=8000)
    assert log.read_text(encoding="utf-8").startswith("earlier backend output\n")


def test_the_line_is_shaped_like_the_backends_own_lines(log: Path) -> None:
    """It is read interleaved with them, so a differently-shaped line breaks the eye scanning for
    a timestamp — and any tooling that reads the log by prefix."""
    record_stop_request(cwd=None, port=8000)
    line = log.read_text(encoding="utf-8").strip()
    assert line[:4].isdigit() and line[4] == "-", line
    assert " INFO " in line


# ── it must never break a stop ───────────────────────────────────────────────


def test_an_unwritable_location_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Evidence is not worth failing a stop over; a read-only mount must not block one."""
    blocked = tmp_path / "file-not-a-directory"
    blocked.write_text("", encoding="utf-8")
    monkeypatch.setattr(stop_provenance, "backend_log_path", lambda cwd: blocked / "backend.log")
    record_stop_request(cwd=None, port=8000)


def test_a_resolver_that_fails_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(cwd: Path | None) -> Path:
        raise OSError("no workspace here")

    monkeypatch.setattr(stop_provenance, "backend_log_path", explode)
    record_stop_request(cwd=None, port=8000)


# ── the inference the absence of a record supports ───────────────────────────


def test_every_stop_request_records_itself_before_it_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing one.

    "A drain with no stop request above it was not asked for by this project's tooling" is only a
    sound reading if `stop_backend` records *whatever* it goes on to do — including deciding there is
    nothing to stop. A path that skips the record turns a silent log into misleading evidence.

    The machine's real backends are hidden from this: without that, the test would enumerate live
    processes and could stop one.
    """
    from src.infrastructure.backend import backend_control

    log = tmp_path / ".arch" / "backend.log"
    monkeypatch.setattr(stop_provenance, "backend_log_path", lambda cwd: log)
    monkeypatch.setattr(backend_control, "read_backend_state", lambda cwd: None)
    monkeypatch.setattr(backend_control, "find_arch_backend_instances", lambda: [])

    backend_control.stop_backend(cwd=tmp_path, port=8099)

    assert log.exists(), "a stop request that found nothing still has to say it was made"
    assert "STOP REQUESTED" in log.read_text(encoding="utf-8")
    assert "port=8099" in log.read_text(encoding="utf-8")
