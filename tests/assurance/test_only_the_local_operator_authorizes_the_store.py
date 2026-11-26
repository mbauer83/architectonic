"""Authorizing the running backend to open the confidential store is a local operator's act.

Regression: `POST /api/assurance/reload {"authorize": true}` was accepted from any client that
reached the port, so anything on the network — or a web page in a browser on this machine — could
authorize the process to open the store, given a key in the credential backend.

The round trip is the point: the request `arch-assurance unlock` builds is replayed against the
route, so the header the command line writes and the one the route reads cannot drift apart.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.assurance import store_factory
from src.infrastructure.backend.arch_backend_app import _build_app

_LOOPBACK_CLIENT = ("127.0.0.1", 50123)
_REMOTE_CLIENT = ("10.20.20.99", 50123)


@pytest.fixture
def authorizations(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    granted: list[str] = []
    monkeypatch.setattr(store_factory, "authorize_process", lambda: granted.append("authorize"))
    monkeypatch.setattr(store_factory, "revoke_process_authorization", lambda: granted.append("revoke"))
    yield granted


def _cli_request(monkeypatch: pytest.MonkeyPatch, *, authorize: bool) -> urllib.request.Request:
    """The request `arch-assurance unlock` / `lock` sends, captured instead of sent."""
    from src.infrastructure.assurance.activation import notify_backend_reload
    from src.infrastructure.cli import _workspace_backend, backend_write

    captured: list[urllib.request.Request] = []
    monkeypatch.setattr(_workspace_backend, "workspace_backend_url", lambda cwd=None: "http://127.0.0.1:8188")

    def _capture(request: urllib.request.Request, timeout: float = 0) -> object:
        captured.append(request)
        raise OSError("captured, not sent")

    monkeypatch.setattr(backend_write, "urlopen", _capture)
    notify_backend_reload(authorize=authorize)
    assert len(captured) == 1
    return captured[0]


def _replay(request: urllib.request.Request, *, client: tuple[str, int]) -> int:
    test_client = TestClient(_build_app(), base_url="http://127.0.0.1:8188", client=client)
    response = test_client.post(
        "/api/assurance/reload", content=request.data, headers=dict(request.header_items()),
    )
    return response.status_code


@pytest.mark.parametrize("authorize", [True, False])
def test_the_command_lines_request_is_accepted_from_the_loopback(
    monkeypatch: pytest.MonkeyPatch, authorizations: list[str], authorize: bool,
) -> None:
    request = _cli_request(monkeypatch, authorize=authorize)

    assert _replay(request, client=_LOOPBACK_CLIENT) == 200
    assert authorizations == ["authorize" if authorize else "revoke"]


def test_the_same_request_from_another_host_is_refused(
    monkeypatch: pytest.MonkeyPatch, authorizations: list[str],
) -> None:
    request = _cli_request(monkeypatch, authorize=True)

    assert _replay(request, client=_REMOTE_CLIENT) == 403
    assert authorizations == []


def test_a_loopback_request_without_the_header_is_refused(authorizations: list[str]) -> None:
    """What a web page in the operator's browser can send: same machine, no custom header."""
    client = TestClient(_build_app(), base_url="http://127.0.0.1:8188", client=_LOOPBACK_CLIENT)

    response = client.post("/api/assurance/reload", json={"authorize": True})

    assert response.status_code == 403
    assert response.json()["detail"]["details"]["reason_code"] == "operator_request_required"
    assert authorizations == []


def test_a_plain_reload_stays_open_to_any_caller(authorizations: list[str]) -> None:
    client = TestClient(_build_app(), base_url="http://127.0.0.1:8188", client=_REMOTE_CLIENT)

    assert client.post("/api/assurance/reload", json={}).status_code == 200
    assert authorizations == []
