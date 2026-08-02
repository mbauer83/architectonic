"""A backend serving the generated fixture workspace, on its own port, for the duration of a walk.

The other half of the write fixture. `fixture_workspace` builds a repository that may be destroyed;
this serves it, so the three write walks can address a *running product* rather than a directory. All
three need exactly this and none of them should own it: the REST register walks HTTP, the MCP walk
speaks JSON-RPC over the same process, and the GUI harness drives the same origin through the real
adapters.

**Its own port, always.** A walk that wrote through `:8000` would be writing into whatever repository
the developer's backend is serving — the live self-model. Port 0 is bound and released to find a free
one, so no walk can collide with a running dev backend.

**One at a time, and the product decides that, not this module.** `arch_backend`'s pre-start guard is
keyed on the *workspace*: if a backend is registered for it and answering, a second invocation prints
"backend already running on port N" and **exits 0**, whatever `--port` says. So two fixture backends
cannot coexist — a second one does not fail, it silently does not start, and a walk would then run
against the first one's content. Found the hard way, by a test that opened two.

Rather than argue with that guard, this serialises against it with a cross-process lock, the same way
`tests/conftest.py` bounds the PlantUML JVM at its one acquisition point. The consequence for the write
walks is worth stating plainly: they **share one fixture backend** rather than each starting its own.

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


@contextlib.contextmanager
def fixture_backend(root: Path | None = None) -> Iterator[FixtureBackend]:
    """Build a fixture workspace, serve it on a free port, and stop the process on the way out.

    `root=None` uses a temporary directory removed afterwards, which is the normal case: the content
    is disposable by design and a walk that leaves a repository behind will have someone point a
    backend at it by accident. Pass a path to keep the workspace for inspection after a failure.
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
            ],
            cwd=str(REPO_ROOT),
            stdout=sink,
            stderr=subprocess.STDOUT,
            # Without this the child inherits the developer's roots and would serve the live model
            # whatever the flags say — the one mistake this module exists to make impossible.
            env={**os.environ, "ARCH_REPO_ROOT": str(workspace.engagement_root),
                 "ARCH_ENTERPRISE_ROOT": str(workspace.enterprise_root)},
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
