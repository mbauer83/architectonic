"""A backend serving the generated fixture workspace, on its own port, for the duration of a walk.

The other half of the write fixture. `fixture_workspace` builds a repository that may be destroyed;
this serves it, so the three write walks can address a *running product* rather than a directory. All
three need exactly this and none of them should own it: the REST register walks HTTP, the MCP walk
speaks JSON-RPC over the same process, and the GUI harness drives the same origin through the real
adapters.

**Its own port, always.** A walk that wrote through `:8000` would be writing into whatever repository
the developer's backend is serving — the live self-model. Port 0 is bound and released to find a free
one, so no walk can collide with a running dev backend.

**One at a time, enforced here.** `arch_backend`'s pre-start guard reads the backend registered for the
*state directory*, and if one is answering it prints "backend already running on port N" and **exits
0**, whatever `--port` says — it does not fail, it silently does not start, and a walk would then talk
to that backend's content believing it had its own. Found the hard way, by a test that opened two.

The state directory is this module's to choose (`ARCH_BACKEND_STATE_DIR`, see `_child_env`), and it
chooses one inside the fixture workspace — so the guard now compares fixture backends with fixture
backends, and the developer's own backend is neither consulted nor overwritten. What keeps it to one is
therefore this module's cross-process lock, the same way `tests/conftest.py` bounds the PlantUML JVM at
its one acquisition point. Worth stating plainly: the write walks **share one fixture backend** rather
than each starting its own, and that is a deliberate bound on a developer machine rather than a
limitation of the product.

**Started as a subprocess, not in-process.** A `TestClient` app would be a different object from the
served one: no uvicorn lifespan, no teardown steps, no real transport. The defects this release found
were all values crossing a boundary, and an in-process app removes the boundary. The cost is a process
to wait for and to stop, which is what the rest of this module is.

Usage:

    with fixture_backend() as backend:
        walk(backend.base_url)          # a real product, serving disposable content
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.quality.fixture_workspace import FixtureWorkspace, build_fixture_workspace  # noqa: E402

#: How long to wait for the process to answer. Generous: the first request builds the index, and this
#: runs on developer machines under load rather than on dedicated CI hardware.
STARTUP_TIMEOUT_SECONDS = 90.0
#: How long to let it stop politely before insisting. The shutdown contract's own budget is smaller.
SHUTDOWN_TIMEOUT_SECONDS = 30.0
#: Probed to decide the process is up. A route that reads the model, so a 200 means the index loaded —
#: `/` would answer from the static bundle before the repository was readable.
READY_PATH = "/api/stats"
#: Held for a fixture backend's whole lifetime. In the xdist-shared temp root so every worker — and a
#: walk run by hand alongside the suite — contends for the same one.
_LOCK_PATH = Path(tempfile.gettempdir()) / "arch-fixture-backend.lock"


@dataclass(frozen=True)
class FixtureBackend:
    """A running backend and the workspace it serves."""

    base_url: str
    port: int
    workspace: FixtureWorkspace
    #: Where the process's combined output goes — read it when a walk fails for reasons it cannot see.
    log: Path


def _free_port() -> int:
    """Bind port 0, read what the kernel gave, release it.

    Racy in principle — something could take the port between release and bind — and correct in
    practice for a developer machine. The alternative, a fixed port, is *reliably* wrong: it collides
    with the dev backend this exists to stay away from.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _await_ready(base_url: str, process: subprocess.Popen[bytes], log: Path, deadline: float) -> None:
    """Wait for the process to serve, or say why it never will.

    Checks liveness each round, so a process that died during startup reports *that* rather than
    timing out — a 90-second wait on a process that exited two seconds in is the slowest possible way
    to learn nothing.
    """
    last_error = "no attempt made"
    while time.monotonic() < deadline:
        if (code := process.poll()) is not None:
            raise RuntimeError(
                f"fixture backend exited with {code} before serving:\n"
                f"{log.read_text(encoding='utf-8', errors='replace')[-4000:]}"
            )
        try:
            with urllib.request.urlopen(f"{base_url}{READY_PATH}", timeout=5) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(
        f"fixture backend did not answer {READY_PATH} in {STARTUP_TIMEOUT_SECONDS}s: {last_error}\n"
        f"{log.read_text(encoding='utf-8', errors='replace')[-4000:]}"
    )


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Ask, then insist.

    `terminate` rather than `arch-backend --stop`: that command finds the backend registered for the
    *workspace*, which is the developer's, not this one. SIGTERM is what the shutdown contract listens
    for, so the teardown steps — including the artifact index close — run the way they do in
    production.
    """
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def state_dir_for(workspace: FixtureWorkspace) -> Path:
    """Where the fixture backend registers itself. Inside its own workspace, never the developer's."""
    return workspace.root / ".arch"


def _child_env(workspace: FixtureWorkspace) -> dict[str, str]:
    """The environment that keeps the child inside the workspace it is meant to serve.

    Three variables, and each one is a mistake this module exists to make impossible.

    ``ARCH_REPO_ROOT`` / ``ARCH_ENTERPRISE_ROOT``: without them the child inherits the developer's
    roots and serves the live model whatever the flags say.

    ``ARCH_BACKEND_STATE_DIR``: without it the child resolves its state directory from *cwd*, which is
    the repository root — so it read, wrote and deleted the developer's `.arch/backend.pid`.
    Two consequences, and the first hid the second. A dev backend registered there made
    `_guard_prestart` find it, print "backend already running on port 8000" and **exit 0**, so the whole
    write-walk suite failed whenever a developer had a backend up — which is the state running the
    browser suite requires. And with no dev backend, the guard passed and the child *overwrote* that
    file with its own pid and port for the length of the walk, then deleted it on the way out.

    The seam was already there: `backend_state._state_dir` checks this variable before anything else.
    """
    return {
        **os.environ,
        "ARCH_REPO_ROOT": str(workspace.engagement_root),
        "ARCH_ENTERPRISE_ROOT": str(workspace.enterprise_root),
        "ARCH_BACKEND_STATE_DIR": str(state_dir_for(workspace)),
    }


@contextlib.contextmanager
def fixture_backend(root: Path | None = None, *, admin_mode: bool = False) -> Iterator[FixtureBackend]:
    """Build a fixture workspace, serve it on a free port, and stop the process on the way out.

    `root=None` uses a temporary directory removed afterwards, which is the normal case: the content
    is disposable by design and a walk that leaves a repository behind will have someone point a
    backend at it by accident. Pass a path to keep the workspace for inspection after a failure.

    `admin_mode=True` adds `--admin-mode`, which opens `/admin/api/*` — the enterprise write surface.
    It is process-wide: one backend cannot be both, and `_require_admin` answers 403 rather than
    pretending. So the admin operations need a **second, sequential** run rather than more steps in the
    first one, and the cross-process lock is what makes "sequential" true rather than hoped for.
    """
    with contextlib.ExitStack() as stack:
        # Taken before the workspace is built, so a waiting walk does not generate content it then
        # cannot serve. Blocking rather than failing: a second walk should queue, not lose its turn.
        guard = stack.enter_context(_LOCK_PATH.open("w"))
        fcntl.flock(guard, fcntl.LOCK_EX)
        stack.callback(fcntl.flock, guard, fcntl.LOCK_UN)

        if root is None:
            root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="arch-fixture-")))
        workspace = build_fixture_workspace(root)
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"

        # A file rather than a pipe. A `PIPE` nobody drains can fill and block the child, and its
        # reader has to be closed by hand — I left that out first time round and it surfaced as
        # `ResourceWarning: unclosed file`, which is the same leak the artifact index had.
        log = Path(stack.enter_context(tempfile.NamedTemporaryFile(
            prefix="arch-fixture-backend-", suffix=".log", delete=True,
        )).name)
        sink = stack.enter_context(log.open("wb"))

        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                "-m",
                "src.infrastructure.backend.arch_backend",
                "--repo-root",
                str(workspace.engagement_root),
                "--enterprise-root",
                str(workspace.enterprise_root),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                *(["--admin-mode"] if admin_mode else []),
            ],
            cwd=str(REPO_ROOT),
            stdout=sink,
            stderr=subprocess.STDOUT,
            env=_child_env(workspace),
        )
        stack.callback(_stop, process)
        _await_ready(base_url, process, log, time.monotonic() + STARTUP_TIMEOUT_SECONDS)
        yield FixtureBackend(base_url=base_url, port=port, workspace=workspace, log=log)


def main(argv: list[str] | None = None) -> int:
    """Serve a fixture workspace until interrupted — for driving a walk by hand."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--root", type=Path, default=None, help="keep the workspace here")
    args = parser.parse_args(argv)

    with fixture_backend(args.root) as backend:
        print(f"fixture backend serving {backend.workspace.engagement_root}")
        print(f"  {backend.base_url}")
        print("  Ctrl-C to stop")
        with contextlib.suppress(KeyboardInterrupt):
            while True:
                time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
