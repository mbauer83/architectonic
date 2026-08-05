"""`arch-assurance status` must report the store's real state, not an artefact of how it asked.

Two ways of getting this wrong, both regressed here. Reporting a freshly built store's in-memory
lock state says `unlocked: false` however activated the store is. Reporting whether the *CLI's own*
process could open the store answers a question nobody has — a CLI invocation is a short-lived
process of its own, and under the manual activation policy no such process is authorized, so an
operator would see `locked` immediately after a successful `unlock`.

What it reports instead is whether a process is holding the store open: the running backend if one
answers, otherwise what a newly started process would do — which the activation policy decides, so
the answer legitimately differs between `manual` and `persistent`.

Also covers `lock` clearing the activation gate.

The autouse `_in_memory_credential_store` fixture (tests/assurance/conftest.py) isolates the
keychain, so these never touch the real OS credential store.
"""

from __future__ import annotations

import argparse

import pytest

from src.config import storage_settings
from src.infrastructure.cli import _assurance_commands as ac

#: Captured before the autouse fixture below replaces the module attribute with a stub.
_REAL_NOTIFY_BACKEND_RELOAD = ac._notify_backend_reload


@pytest.fixture(autouse=True)
def _force_sqlcipher_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage_settings, "storage_assurance_store_backend", lambda: "sqlcipher")
    monkeypatch.setattr(storage_settings, "storage_assurance_signals_backend", lambda: "sqlcipher-colocated")
    monkeypatch.setattr(storage_settings, "storage_assurance_archive_backend", lambda: "standard")
    monkeypatch.setattr(storage_settings, "storage_assurance_max_classification", lambda: "TLP:RED")
    # Keep cmd_unlock/cmd_lock from blocking on a real backend reload POST. Accepts whatever
    # authorization intent the command passes, so the stub cannot go stale against the signature.
    monkeypatch.setattr(ac, "_notify_backend_reload", lambda **_kwargs: None)


@pytest.fixture(autouse=True)
def _no_backend_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """No backend is running in a unit test, so status falls through to the next-process question.

    Stubbed rather than left to time out: the real probe would wait on a socket, and a developer
    with a backend running on the default port would otherwise get different results.
    """
    from src.infrastructure.cli import _assurance_status as status

    monkeypatch.setattr(status, "backend_holds_store_open", lambda: None)


def _set_policy(monkeypatch: pytest.MonkeyPatch, policy: str) -> None:
    from src.infrastructure.assurance import store_factory

    monkeypatch.setattr(
        store_factory.storage_settings, "storage_assurance_activation_policy", lambda: policy,
    )
    monkeypatch.setattr(storage_settings, "storage_assurance_activation_policy", lambda: policy)


pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


def _init(db_path) -> None:  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance.lifecycle import init_store

    init_store(db_path)


def test_an_activated_store_reads_as_unlocked_where_a_new_process_opens_it(
    tmp_path, capsys, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    """Under `persistent` a newly started process opens an activated store, so status says so.

    This is the case that catches reporting a bare store's in-memory lock state, which would read
    `unlocked: false` here however activated the store is.
    """
    _set_policy(monkeypatch, "persistent")
    db = tmp_path / "store.db"
    _init(db)
    args = argparse.Namespace(db_path=str(db))

    assert ac.cmd_unlock(args) == 0
    capsys.readouterr()

    assert ac.cmd_status(args) == 0
    out = capsys.readouterr().out
    assert "unlocked: true" in out
    assert "status: unlocked" in out
    assert "activation_policy: persistent" in out


def test_an_activated_store_reads_as_locked_where_each_process_is_authorized_by_hand(
    tmp_path, capsys, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    """Under `manual` nothing holds an activated store open until a process is authorized.

    Reporting `unlocked: true` here would be the more dangerous error of the two: it would claim
    access is open when no process has any.
    """
    _set_policy(monkeypatch, "manual")
    db = tmp_path / "store.db"
    _init(db)
    args = argparse.Namespace(db_path=str(db))

    assert ac.cmd_unlock(args) == 0
    capsys.readouterr()

    assert ac.cmd_status(args) == 0
    out = capsys.readouterr().out
    assert "unlocked: false" in out
    assert "status: locked" in out
    assert "setup_confirmed: true" in out, "the store is activated — that is a separate fact"
    assert "arch-assurance unlock" in out, "the note must say what would open it"


def test_a_running_backend_holding_the_store_open_is_what_status_reports(
    tmp_path, capsys, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    """The backend serving the capability is the process an operator is asking about."""
    from src.infrastructure.cli import _assurance_status as status

    _set_policy(monkeypatch, "manual")
    monkeypatch.setattr(status, "backend_holds_store_open", lambda: True)
    db = tmp_path / "store.db"
    _init(db)
    args = argparse.Namespace(db_path=str(db))
    assert ac.cmd_unlock(args) == 0
    capsys.readouterr()

    assert ac.cmd_status(args) == 0
    out = capsys.readouterr().out
    assert "unlocked: true" in out
    assert "status: unlocked" in out


def test_lock_disables_auto_unlock(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "store.db"
    _init(db)
    args = argparse.Namespace(db_path=str(db))
    assert ac.cmd_unlock(args) == 0
    capsys.readouterr()

    assert ac.cmd_lock(args) == 0
    capsys.readouterr()

    assert ac.cmd_status(args) == 0
    out = capsys.readouterr().out
    assert "unlocked: false" in out
    assert "setup_confirmed: false" in out
    assert "locked_needs_activation" in out


# ── Which backend an assurance command talks to ───────────────────────────────
#
# `unlock` posts `authorize: true`. Composed from the configured port, that reached whichever process
# held it — so on a machine running two workspaces, one workspace's unlock ceremony authorized the
# *other* workspace's backend to open its own confidential store. The endpoint has to be the backend
# that reports serving this workspace's repositories, and nothing at all when none does.


def test_an_assurance_command_talks_to_the_backend_serving_this_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from src.domain.deployment.backend_endpoint import AttachToBackend
    from src.infrastructure.cli import _workspace_backend

    monkeypatch.setattr(_workspace_backend, "configured_backend_url", lambda: None)
    monkeypatch.setattr(
        _workspace_backend, "plan_workspace_endpoint", lambda **_kwargs: AttachToBackend(port=8188)
    )

    assert _workspace_backend.workspace_backend_url(cwd=tmp_path) == "http://127.0.0.1:8188"


def test_no_backend_serving_this_workspace_means_no_url_at_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Not a fallback to the configured port: that port may be a neighbour's backend."""
    from src.domain.deployment.backend_endpoint import RefuseEndpoint
    from src.infrastructure.cli import _workspace_backend

    monkeypatch.setattr(_workspace_backend, "configured_backend_url", lambda: None)
    monkeypatch.setattr(
        _workspace_backend,
        "plan_workspace_endpoint",
        lambda **_kwargs: RefuseEndpoint(reason="port 8000 is serving another workspace (/elsewhere)"),
    )

    assert _workspace_backend.workspace_backend_url(cwd=tmp_path) is None


def test_an_externally_named_backend_is_used_as_given(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from src.infrastructure.cli import _workspace_backend

    monkeypatch.setattr(_workspace_backend, "configured_backend_url", lambda: "http://backend.internal:8000")

    assert _workspace_backend.workspace_backend_url(cwd=tmp_path) == "http://backend.internal:8000"


def test_unlock_authorizes_nothing_when_no_backend_serves_this_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The authorization POST is what makes this a confidentiality question, not a convenience one.

    Driven through `_REAL_NOTIFY_BACKEND_RELOAD`, captured at import: the autouse fixture above
    replaces the module attribute, so calling it by name here would exercise the stub.
    """
    import urllib.request

    from src.infrastructure.cli import _workspace_backend

    posted: list[str] = []
    monkeypatch.setattr(_workspace_backend, "workspace_backend_url", lambda cwd=None: None)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: posted.append("posted"))

    _REAL_NOTIFY_BACKEND_RELOAD(authorize=True)

    assert posted == []


def test_unlock_authorizes_the_backend_serving_this_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    from src.infrastructure.cli import _workspace_backend

    urls: list[str] = []
    monkeypatch.setattr(_workspace_backend, "workspace_backend_url", lambda cwd=None: "http://127.0.0.1:8188")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=3: urls.append(req.full_url) or _Response()
    )

    _REAL_NOTIFY_BACKEND_RELOAD(authorize=True)

    assert urls == ["http://127.0.0.1:8188/api/assurance/reload"]
