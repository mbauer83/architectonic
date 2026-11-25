"""A writing CLI command locates its backend as the assurance commands do, then checks what it serves.

Regression: `arch-exchange import --commit`, `arch-icons import` and the delete commands located the
backend from the recorded state file alone, so they ignored `ARCH_MCP_BACKEND_URL` — the backend a
container or a remote setup names — while `arch-assurance` honoured it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.deployment.endpoint_vocabulary import BackendIdentity
from src.infrastructure.cli import _workspace_backend, backend_write
from src.infrastructure.cli._workspace_backend import AttachedBackend, NamedBackend

_AT = "http://127.0.0.1:8137"


def test_a_named_backend_is_the_one_written_to(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCH_MCP_BACKEND_URL", "http://backend.internal:8000/")

    assert _workspace_backend.workspace_backend(cwd=tmp_path) == NamedBackend("http://backend.internal:8000")
    assert backend_write.serving_url(tmp_path) == "http://backend.internal:8000"


def test_an_attached_backend_must_serve_the_engagement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serving = BackendIdentity((str(tmp_path.resolve()),), "test")
    monkeypatch.setattr(backend_write, "workspace_backend", lambda cwd: AttachedBackend(_AT, serving))

    assert backend_write.serving_url(tmp_path) == _AT


def test_an_attached_backend_serving_another_engagement_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    neighbour = BackendIdentity((str(tmp_path / "other"), str(tmp_path)), "test")
    monkeypatch.setattr(backend_write, "workspace_backend", lambda cwd: AttachedBackend(_AT, neighbour))

    with pytest.raises(backend_write.BackendWriteError, match="does not serve"):
        backend_write.serving_url(tmp_path)


def test_an_attached_backend_that_did_not_say_is_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def identity_at(url: str) -> BackendIdentity:
        asked.append(url)
        return BackendIdentity((str(tmp_path.resolve()),), "test")

    monkeypatch.setattr(backend_write, "workspace_backend", lambda cwd: AttachedBackend(_AT, None))
    monkeypatch.setattr(backend_write, "probe_backend_identity", identity_at)

    assert backend_write.serving_url(tmp_path) == _AT
    assert asked == [_AT]
