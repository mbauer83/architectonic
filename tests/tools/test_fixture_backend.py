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
from typing import Any

import pytest

from tools.quality.fixture_backend import FixtureBackend, fixture_backend


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
