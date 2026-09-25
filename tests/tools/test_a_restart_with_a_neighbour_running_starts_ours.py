"""A restart with no backend of this workspace running starts one, even while a neighbour's is up."""

from __future__ import annotations

import pytest

from src.infrastructure.backend import _lifecycle_cli, backend_control


def _stop_answers(monkeypatch: pytest.MonkeyPatch, answer: dict[str, object]) -> None:
    monkeypatch.setattr(backend_control, "stop_backend", lambda port=None: answer)


def test_a_neighbours_backend_is_not_ours_to_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _stop_answers(monkeypatch, {"stopped": False, "reason": "foreign_workspace", "port": 8000, "served_roots": ["/x"]})

    _lifecycle_cli._stop_for_restart(8020)


def test_nothing_running_is_nothing_to_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _stop_answers(monkeypatch, {"stopped": False, "reason": "not_running"})

    _lifecycle_cli._stop_for_restart(8020)


def test_a_backend_that_would_not_stop_still_refuses_the_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    _stop_answers(monkeypatch, {"stopped": False, "reason": "timeout", "pid": 42})

    with pytest.raises(SystemExit, match="failed to restart backend pid 42"):
        _lifecycle_cli._stop_for_restart(8020)
