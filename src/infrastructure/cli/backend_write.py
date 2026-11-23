"""Send CLI mutations only to the backend that serves the requested engagement."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.infrastructure.backend.backend_endpoint import claim_for_roots, port_serves_workspace
from src.infrastructure.backend.backend_probe import backend_url, probe_backend
from src.infrastructure.backend.backend_state import read_backend_state


class BackendWriteError(RuntimeError):
    """A command could not reach the intended backend or complete its request."""


class BackendRefusal(BackendWriteError):
    """The server received the request and refused it."""


def serving_port(root: Path) -> int:
    state = read_backend_state(root)
    if state is None or not probe_backend(state["port"]):
        raise BackendWriteError(f"Start arch-backend --daemon for {root} before issuing this command.")
    port = state["port"]
    if not port_serves_workspace(port, claim_for_roots(root, None)):
        raise BackendWriteError(f"The backend on port {port} does not serve {root}; refusing to send a write to it.")
    return port


def post(port: int, path: str, body: bytes, content_type: str) -> dict[str, Any]:
    request = Request(f"{backend_url(port)}{path}", data=body,
                      headers={"Content-Type": content_type, "Accept": "application/json"}, method="POST")
    return send(request, timeout=300)


def send(request: Request, *, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read()
            return json.loads(body) if body.strip() else {}
    except HTTPError as exc:
        with exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
        raise BackendRefusal(detail or str(exc)) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise BackendWriteError(f"Backend proxy failed: {exc}") from exc
