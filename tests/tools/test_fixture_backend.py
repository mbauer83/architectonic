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
import os
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

    def test_its_credential_store_is_a_throwaway_inside_the_workspace(
        self, backend: FixtureBackend
    ) -> None:
        """The same isolation, for the other piece of global state a backend reaches for.

        `tests/conftest.py` redirects the credential directory for the whole suite and says why:
        subprocesses inherit the env, so a child that copies it is hermetic and a child run outside
        pytest is not. A fixture backend started by hand had neither variable set, so `_get_backend`
        selected the real OS backend and the served `/api/assurance/status` read the developer's own
        credential accounts on every call.

        Set here rather than left to the caller, because the fixture backend is the thing that knows it
        owns a disposable workspace. And a master password rather than the forbid flag: the forbid check
        precedes the password branch and raises, so forbidding leaves no credential store at all.
        """
        from tools.quality.fixture_backend import _child_env

        env = _child_env(backend.workspace)
        credentials = Path(env["ARCH_ASSURANCE_CREDENTIALS_DIR"])

        assert credentials.is_relative_to(backend.workspace.root), credentials
        assert not credentials.is_relative_to(Path.home() / ".config"), credentials
        assert env["ARCH_ASSURANCE_MASTER_PASSWORD"], env

        # And the forbid flag is *absent*, which is the one combination that cannot work: the check
        # precedes the password branch in `_get_backend` and raises, so a child carrying both has no
        # credential store at all rather than a throwaway one.
        #
        # Absent, not merely un-added. This suite sets the flag for every test and children inherit the
        # environment, so `assurance_child_env` now pops it — which is what lets the store builder run
        # under pytest at all. Asserted against the parent actually having it set, or the interesting
        # half of the claim would be vacuous.
        assert os.environ.get("ARCH_ASSURANCE_FORBID_REAL_CREDENTIAL_BACKEND"), (
            "the suite-wide forbid flag is unset, so this test proves nothing about removing it"
        )
        assert "ARCH_ASSURANCE_FORBID_REAL_CREDENTIAL_BACKEND" not in env, sorted(env)

    def test_its_assurance_store_is_the_fixture_one_and_it_is_open(
        self, backend: FixtureBackend
    ) -> None:
        """The store half of "served content is generated content", and it needs a discriminator.

        `unlocked: true` alone would be satisfied by the *developer's* store, which is unlocked on this
        machine — so what distinguishes them is the content, and the discriminator is equality rather
        than a bound. The dogfood store holds tens of nodes across several analyses; this one holds
        exactly the nodes the fixture authored, which no other store can.

        An exact set is legitimate here for the reason `CLAUDE.md` gives: the test owns the content. The
        rule against exact counts is about the *live* model, where authoring one more node is the
        product working.

        Both halves matter. Locked-but-fixture would fail every assurance walk step with a 423, and
        unlocked-but-live would let one author into the analyst's evidence.
        """
        status = _get(backend, "/api/assurance/status")
        assert status["configured"] is True, status
        assert status["unlocked"] is True, status

        authored = backend.workspace.authored
        expected = {
            authored[role][0]
            for role in ("assurance_hazard_node", "assurance_bare_node", "assurance_failure_mode")
        }
        # `nodes`, not `items`: the assurance list contracts name their own collection, so the generic
        # `_items` helper falls through to the envelope and iterating it yields keys.
        payload = _get(backend, "/api/assurance/nodes")
        served = {str(node["node_id"]) for node in payload["nodes"]}
        assert served == expected, sorted(served ^ expected)

    def test_the_store_it_serves_is_not_the_developers(self, backend: FixtureBackend) -> None:
        """Stated as a path claim as well, because the content claim above is only circumstantial.

        The manifest resolves `assurance_db_path` from `ARCH_ASSURANCE_DB_PATH` with `env` provenance,
        so what the child resolves is what the fixture set. Asserting it here keeps a future default
        change from quietly moving the served store back into the source tree while the emptiness
        assertion above still passed — which it would, on a store nobody had written to yet.
        """
        from tools.quality.fixture_backend import _child_env

        served = Path(_child_env(backend.workspace)["ARCH_ASSURANCE_DB_PATH"])

        assert served.is_relative_to(backend.workspace.root), served
        assert not served.is_relative_to(REPO_ROOT), served

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
