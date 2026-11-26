"""A git worktree is a workspace of its own, even when it lives inside another checkout.

The defect: `arch-backend --daemon` run from `.claude/worktrees/<name>` found the main checkout's
backend on the shared default port and declined to start, calling it this workspace's own. The
worktree carries the tracked `arch-workspace.yaml` but not the gitignored `.arch/init-state.yaml`,
and the search for that state walked up past the worktree into the enclosing checkout — so the
worktree claimed the main checkout's repositories, and the main checkout's backend, asked what it
serves, answered truthfully with exactly those.

The fixtures are real: one repository, a `git worktree add` nested inside it the way agent worktrees
are, and a second worktree beside it. The socket tests run fake backends on free ports, with no
probe stubbed, because the identity comparison over HTTP is the mechanism under test.
"""

from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from src.config.workspace_paths import load_workspace_state, resolve_workspace_repo_roots
from src.domain.deployment.backend_endpoint import (
    AttachToBackend,
    PortPreference,
    StartBackendOn,
    WorkspaceClaim,
    derived_port,
)
from src.infrastructure.backend import backend_endpoint
from src.infrastructure.backend.backend_state import backend_start_lock_path, backend_state_path


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def checkouts(tmp_path: Path) -> dict[str, Path]:
    """A main checkout with init state, a worktree nested inside it, and one beside it."""
    main = tmp_path / "main"
    for repo in ("engagement", "enterprise"):
        (main / repo).mkdir(parents=True)
        (main / repo / "README.md").write_text(repo, encoding="utf-8")
    (main / "arch-workspace.yaml").write_text(
        yaml.safe_dump({"engagement": {"local": "engagement"}, "enterprise": {"local": "enterprise"}}),
        encoding="utf-8",
    )
    (main / ".gitignore").write_text(".arch/\n.claude/\n", encoding="utf-8")
    _git(main, "init", "-q", "-b", "main")
    _git(main, "add", ".")
    _git(main, "commit", "-q", "-m", "init")

    (main / ".arch").mkdir()
    (main / ".arch" / "init-state.yaml").write_text(
        yaml.safe_dump(
            {
                "workspace_root": str(main.resolve()),
                "engagement_root": str((main / "engagement").resolve()),
                "enterprise_root": str((main / "enterprise").resolve()),
                "initialized_at": "2026-11-26T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    nested = main / ".claude" / "worktrees" / "agent"
    beside = tmp_path / "beside"
    _git(main, "worktree", "add", "-q", "-b", "nested", str(nested))
    _git(main, "worktree", "add", "-q", "-b", "beside", str(beside))
    return {"main": main, "nested": nested, "beside": beside}


def _own_claim(checkout: Path) -> WorkspaceClaim:
    return WorkspaceClaim(
        engagement_root=(checkout / "engagement").resolve(),
        enterprise_root=(checkout / "enterprise").resolve(),
    )


# ── what each checkout claims ─────────────────────────────────────────────────


def test_a_nested_worktree_does_not_read_the_enclosing_checkouts_init_state(checkouts) -> None:
    assert load_workspace_state(checkouts["nested"]) is None
    assert load_workspace_state(checkouts["nested"] / "engagement") is None


def test_each_checkout_claims_its_own_repositories(checkouts) -> None:
    claims = {name: backend_endpoint.workspace_claim(path) for name, path in checkouts.items()}

    for name, path in checkouts.items():
        assert claims[name] == _own_claim(path)
    assert len({claim.fingerprint for claim in claims.values() if claim is not None}) == 3


def test_a_nested_worktree_serves_its_own_repositories(checkouts) -> None:
    """The backend process resolves what it serves through the same reading as the claim."""
    nested = checkouts["nested"]

    assert resolve_workspace_repo_roots(nested) == (
        (nested / "engagement").resolve(),
        (nested / "enterprise").resolve(),
    )


def test_the_main_checkout_still_reads_its_init_state(checkouts) -> None:
    main = checkouts["main"]

    assert load_workspace_state(main / "engagement") is not None
    assert backend_endpoint.workspace_claim(main / "engagement") == _own_claim(main)


def test_each_checkout_keeps_its_backend_record_in_its_own_state_directory(checkouts, monkeypatch) -> None:
    monkeypatch.delenv("ARCH_BACKEND_STATE_DIR", raising=False)
    nested = checkouts["nested"]

    assert backend_state_path(nested) == nested.resolve() / ".arch" / "backend.pid"
    # From a subdirectory too: the worktree's root is the directory declaring it.
    assert backend_start_lock_path(nested / "engagement") == nested.resolve() / ".arch" / "backend-start.lock"
    assert backend_state_path(checkouts["main"]) != backend_state_path(nested)


# ── over real sockets ─────────────────────────────────────────────────────────


@pytest.fixture
def serve_backend():
    """A fake backend publishing one checkout's roots on a free port; stopped on teardown."""
    servers: list[ThreadingHTTPServer] = []

    def start(checkout: Path) -> int:
        claim = _own_claim(checkout)
        roots = [str(claim.engagement_root), str(claim.enterprise_root)]

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
                if self.path.startswith("/api/backend-identity"):
                    body = {"repo_roots": roots, "software_version": "9.9.9"}
                elif self.path.startswith("/api/stats"):
                    body = {"entities": 0}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return int(server.server_address[1])

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("worktree", ["nested", "beside"])
def test_a_worktree_does_not_take_the_main_checkouts_backend_for_its_own(
    checkouts, serve_backend, worktree: str
) -> None:
    main_port = serve_backend(checkouts["main"])

    plan = backend_endpoint.plan_workspace_endpoint(
        cwd=checkouts[worktree],
        may_start=True,
        preference=PortPreference(port=main_port, authority="settings_document"),
    )

    assert isinstance(plan, StartBackendOn)
    assert plan.moved_from == main_port
    assert plan.moved_because == "foreign"
    assert plan.port == derived_port(_own_claim(checkouts[worktree]).fingerprint)


def test_two_worktrees_do_not_take_each_others_backend(checkouts, serve_backend) -> None:
    beside_port = serve_backend(checkouts["beside"])

    plan = backend_endpoint.plan_workspace_endpoint(
        cwd=checkouts["nested"],
        may_start=True,
        preference=PortPreference(port=beside_port, authority="settings_document"),
    )

    assert isinstance(plan, StartBackendOn)
    assert plan.moved_because == "foreign"


@pytest.mark.parametrize("checkout", ["main", "nested"])
def test_a_checkout_still_finds_its_own_backend(checkouts, serve_backend, checkout: str) -> None:
    own_port = serve_backend(checkouts[checkout])

    plan = backend_endpoint.plan_workspace_endpoint(
        cwd=checkouts[checkout],
        may_start=True,
        preference=PortPreference(port=own_port, authority="settings_document"),
    )

    assert isinstance(plan, AttachToBackend)
    assert plan.port == own_port
