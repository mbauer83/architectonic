"""`arch-assurance unlock` says what the running backend answered, not what it hoped.

A backend started in a shell whose credential backend could not read the key stayed locked, while
`unlock` printed "Store activated and the running backend authorized" and exited 0: the reload's answer
was discarded and the success note was unconditional. The answer is now carried back and decides the
report and the exit status.
"""

from __future__ import annotations

import argparse
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.infrastructure.assurance import _credential_accounts as accounts


def _answering(unlocked: bool) -> type[BaseHTTPRequestHandler]:
    class _Backend(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.dumps({
                "configured": True, "unlocked": unlocked, "db_exists": True, "key_in_keychain": True,
                "status": "unlocked" if unlocked else "locked", "module_class": "assurance",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            pass

    return _Backend


class _Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def unlock(self) -> None: ...

    def stats(self) -> dict[str, int]:
        return {"node_count": 0}

    def lock(self) -> None: ...


@pytest.fixture()
def ceremony(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.infrastructure.assurance._sqlcipher_store as sqlcipher_module

    monkeypatch.setattr(sqlcipher_module, "SQLCipherAssuranceStore", _Store)
    monkeypatch.setattr(accounts, "write", lambda *_a, **_k: None)


@pytest.fixture()
def backend(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Iterator[None]:
    import src.infrastructure.cli._workspace_backend as workspace_backend

    server = HTTPServer(("127.0.0.1", 0), _answering(request.param))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        workspace_backend, "workspace_backend_url", lambda **_k: f"http://127.0.0.1:{server.server_address[1]}",
    )
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()


def _unlock(tmp_path: Path) -> int:
    from src.infrastructure.cli._assurance_commands import cmd_unlock

    return cmd_unlock(argparse.Namespace(db_path=str(tmp_path / "store.db")))


@pytest.mark.parametrize("backend", [False], indirect=True)
@pytest.mark.usefixtures("ceremony", "backend")
def test_a_backend_that_stayed_locked_is_reported_and_fails_the_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    status = _unlock(tmp_path)

    out = capsys.readouterr().out
    assert "running backend authorized" not in out, out
    assert "still locked" in out
    assert "activated_backend_still_locked" in out
    assert status == 1


@pytest.mark.parametrize("backend", [True], indirect=True)
@pytest.mark.usefixtures("ceremony", "backend")
def test_a_backend_that_took_the_store_is_reported_as_authorized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    status = _unlock(tmp_path)

    assert "running backend authorized" in capsys.readouterr().out
    assert status == 0


@pytest.mark.usefixtures("ceremony")
def test_with_no_backend_running_nothing_is_claimed_about_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    import src.infrastructure.cli._workspace_backend as workspace_backend

    monkeypatch.setattr(workspace_backend, "workspace_backend_url", lambda **_k: None)

    status = _unlock(tmp_path)

    out = capsys.readouterr().out
    assert "running backend authorized" not in out
    assert "no backend of this workspace is running" in out
    assert status == 0


@pytest.mark.parametrize("answer", [False, True, None])
def test_the_updater_authorize_phase_fails_when_the_restarted_backend_stays_locked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, answer: bool | None,
) -> None:
    import src.infrastructure.assurance.activation as activation
    from src.infrastructure.software_update.local_actions import LocalCheckoutActions, UpdateActionError

    monkeypatch.setattr(
        activation, "activate_store",
        lambda db_path: activation.StoreActivation(db_path=db_path, stats={}, backend_unlocked=answer),
    )
    actions = LocalCheckoutActions(tmp_path, assets_dir=tmp_path / "assets", deployment_arguments=())

    if answer is False:
        with pytest.raises(UpdateActionError, match="still locked"):
            actions.authorize_store()
    else:
        actions.authorize_store()
