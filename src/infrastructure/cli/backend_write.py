"""Send CLI mutations only to the backend that serves the requested engagement.

The backend is located as every CLI command locates it (`_workspace_backend`): the one
`ARCH_MCP_BACKEND_URL` names, else the one the workspace plan attaches to — which must then report
serving the engagement the command writes to.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.infrastructure.backend.backend_probe import probe_backend_identity
from src.infrastructure.cli._workspace_backend import AttachedBackend, NamedBackend, workspace_backend


class BackendWriteError(RuntimeError):
    """A command could not reach the intended backend or complete its request."""


class BackendRefusal(BackendWriteError):
    """The server received the request and refused it."""


def serving_url(root: Path) -> str:
    """The base URL of the backend serving *root* as its engagement; refused where there is none."""
    match workspace_backend(cwd=root):
        case None:
            raise BackendWriteError(f"Start arch-backend --daemon for {root} before issuing this command.")
        case NamedBackend(url=url):
            return url
        case AttachedBackend(url=url, identity=identity):
            reported = identity or probe_backend_identity(url)
            if reported is None:
                raise BackendWriteError(
                    f"The backend at {url} does not say what it serves. Start arch-backend --daemon for "
                    f"{root} before issuing this command."
                )
            if not reported.serves_engagement(root.resolve()):
                raise BackendWriteError(
                    f"The backend at {url} does not serve {root} as its engagement. Start arch-backend "
                    f"--daemon for {root} before issuing this command."
                )
            return url


def post(base_url: str, path: str, body: bytes, content_type: str) -> dict[str, Any]:
    request = Request(f"{base_url}{path}", data=body,
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
