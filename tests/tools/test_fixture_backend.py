"""The fixture backend serves the disposable workspace, not the developer's repository.

This is the assertion the whole write-fixture idea rests on. A walk that authors and destroys content
is safe only if the process it is talking to is serving the generated workspace; point it at `:8000` by
accident and it edits the live self-model. So the test that matters is not "a backend started" but
"the backend is serving *this* content and nothing else".

One backend for the whole module: starting a real process is the expensive part, and every assertion
below can be made against the same one.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tools.quality.fixture_backend import FixtureBackend, fixture_backend, state_dir_for

REPO_ROOT = Path(__file__).resolve().parents[2]


def state_dir_for_this(backend: FixtureBackend) -> Path:
    return state_dir_for(backend.workspace)


@pytest.fixture(scope="module")
def backend() -> Iterator[FixtureBackend]:
    with fixture_backend() as running:
        yield running


def _get(backend: FixtureBackend, path: str) -> Any:
    with urllib.request.urlopen(f"{backend.base_url}{path}", timeout=30) as response:
        assert response.status == 200, (path, response.status)
        return json.loads(response.read())


def _items(payload: Any) -> list[dict[str, Any]]:
    return payload["items"] if isinstance(payload, dict) and "items" in payload else payload


def test_it_serves_on_its_own_port_not_the_default(backend: FixtureBackend) -> None:
    # 8000 is the developer's. A walk that wrote there would be writing into the live model.
    assert backend.port != 8000
    assert backend.base_url == f"http://127.0.0.1:{backend.port}"


def test_the_entities_it_serves_are_exactly_the_fixture_ones(backend: FixtureBackend) -> None:
    """The load-bearing assertion: served content is generated content.

    A subset check would pass against the live repository, which holds hundreds of entities including
    none named like these — so equality of the id set is what distinguishes the two.
    """
    served = {item["artifact_id"] for item in _items(_get(backend, "/api/entities"))}
    authored = set(backend.workspace.ids("entity")) | {backend.workspace.unreferenced_entity}
    assert served == authored, sorted(served ^ authored)


def test_it_serves_the_fixture_documents_and_diagram(backend: FixtureBackend) -> None:
    documents = {item["artifact_id"] for item in _items(_get(backend, "/api/documents"))}
    assert documents == set(backend.workspace.ids("document")), sorted(documents)
    diagrams = {item["artifact_id"] for item in _items(_get(backend, "/api/diagrams"))}
    assert diagrams == set(backend.workspace.ids("diagram")), sorted(diagrams)


def test_none_of_the_real_repository_is_visible(backend: FixtureBackend) -> None:
    """Named directly, because "serves the fixture" and "does not serve the model" can both be checked
    and only the second one fails loudly if the roots were resolved from the environment instead of the
    flags — which is precisely the mistake `fixture_backend` passes explicit env vars to prevent."""
    served = {item["artifact_id"] for item in _items(_get(backend, "/api/entities"))}
    assert not any(identifier.startswith("REQ@") for identifier in served), sorted(served)
    stats = _get(backend, "/api/stats")
    # The self-model holds hundreds of entities; the fixture holds three.
    total = stats.get("entities") if isinstance(stats.get("entities"), int) else len(served)
    assert total < 20, stats


def test_the_connection_between_the_two_connected_entities_is_served(backend: FixtureBackend) -> None:
    source, _target = backend.workspace.connected_entities
    context = _get(backend, f"/api/entities/{urllib.request.quote(source)}/context")
    connections = context.get("connections") or {}
    outbound = connections.get("outbound") or []
    assert outbound, context


class TestItKeepsOutOfTheDevelopersBackendState:
    """The fixture backend registers itself inside its own workspace, not the developer's `.arch/`.

    `arch-backend` resolves its state directory from cwd unless told otherwise, and this child runs with
    cwd at the repository root — so it used to read, write and delete
    `<repo>/.arch/backend.pid`, the file the developer's own backend registers in.

    Two failures came out of that, and the first hid the second. With a dev backend running, the
    pre-start guard found it there, printed "backend already running on port 8000" and exited **0**:
    every test in this module, both write walks and their suites failed, for as long as a developer had
    a backend up — which is exactly the state `npm run test:e2e` requires. And with no dev backend, the
    guard passed and the child overwrote that file with its own pid and port for the length of a walk,
    then removed it on the way out.

    Both are the same mistake as inheriting the developer's *roots*, which this module already passes
    explicit environment to prevent. It now passes one more. The eviction was observed live: while a dev
    backend served :8000, the repository's `.arch/backend.pid` named a fixture's pid and port instead, so
    `arch-backend --stop` and `--restart` could no longer find the process that was actually running.
    """

    def test_its_state_directory_is_inside_the_workspace_it_serves(
        self, backend: FixtureBackend
    ) -> None:
        from tools.quality.fixture_backend import _child_env, state_dir_for

        state_dir = state_dir_for(backend.workspace)
        assert state_dir.is_relative_to(backend.workspace.root)
        assert _child_env(backend.workspace)["ARCH_BACKEND_STATE_DIR"] == str(state_dir)

    def test_the_repository_and_the_fixture_cannot_resolve_to_one_state_file(
        self, backend: FixtureBackend
    ) -> None:
        """The negative half, and the one that matters: a walk must not evict the developer's backend.

        Asserted as "the two addresses are different and the fixture's is outside the repository",
        rather than by comparing what happens to be in the developer's file. Ports are a poor identity
        for this — the kernel reuses recently-freed ephemeral ports, so a fixture can be handed the very
        port a previous fixture wrote there, and the comparison passes or fails on that.
        """
        from src.infrastructure.backend.backend_state import backend_state_path

        repository_state = backend_state_path(REPO_ROOT)
        fixture_state = state_dir_for_this(backend) / repository_state.name

        assert fixture_state != repository_state
        assert not fixture_state.is_relative_to(REPO_ROOT), fixture_state

    def test_the_variable_it_passes_is_the_one_the_state_reader_obeys(
        self, backend: FixtureBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The positive half, through the reader the pre-start guard itself uses.

        Setting the variable in *this* process and reading is what proves the child's registration is
        discoverable at the address the guard would look at for this workspace — which is the whole
        mechanism, and is what makes the guard compare fixture backends with fixture backends.
        """
        from src.infrastructure.backend.backend_state import read_backend_state
        from tools.quality.fixture_backend import _child_env

        monkeypatch.setenv(
            "ARCH_BACKEND_STATE_DIR", _child_env(backend.workspace)["ARCH_BACKEND_STATE_DIR"]
        )

        state = read_backend_state()
        assert state is not None, "the fixture backend registered nowhere its own guard would look"
        # A mapping, not a dataclass — the pre-start guard reads it with `.get("port")` too.
        assert state["port"] == backend.port, (state, backend.port)


def test_only_one_fixture_backend_can_exist_at_a_time(backend: FixtureBackend) -> None:
    """`arch_backend`'s pre-start guard is keyed on the workspace, so a second one cannot serve.

    This is the constraint, asserted rather than discovered again. A second invocation prints "backend
    already running on port N" and **exits 0** whatever `--port` says — it does not fail, it silently
    does not start, and a walk would then be talking to the first backend's content while believing it
    had its own. `fixture_backend` therefore holds a cross-process lock for its whole lifetime, and the
    write walks share one backend instead of each starting one.

    Asserted by proving the lock is held while a backend is up, rather than by opening a second one:
    opening a second one is exactly what the lock is there to make impossible.
    """
    import fcntl

    from tools.quality.fixture_backend import _LOCK_PATH

    assert _get(backend, "/api/stats"), "the running backend should answer before this is meaningful"
    with _LOCK_PATH.open("w") as contender:
        with pytest.raises(BlockingIOError):
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
