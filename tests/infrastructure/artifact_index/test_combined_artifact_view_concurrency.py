"""Guards REQ@1782080517.IIl8-4 ("Concurrent Reads, Serialized Writes") on the combined-scope
read path: every one of the eleven SQLite-backed ArtifactStorePort methods must dispatch to
both canonical instances concurrently — except `read_entity_context`, which is a fallback (only
one side is ever actually queried) and must therefore short-circuit instead.

Each canned store sleeps `_DELAY` seconds before returning; if a method dispatches
sequentially instead of concurrently, wall time roughly doubles from `_DELAY` to `2 * _DELAY`
— comfortably outside `_SEQUENTIAL_THRESHOLD` below.
"""

from __future__ import annotations

import time
from typing import Any, cast

import pytest

from src.application.ports import ReadableArtifactStore
from src.infrastructure.artifact_index import _combined_support as support
from src.infrastructure.artifact_index.combined_index import CombinedArtifactView

_DELAY = 0.15
_SEQUENTIAL_THRESHOLD = _DELAY * 1.6


class _SlowStore:
    """Test double: every relevant method sleeps `delay` seconds, then returns `value`."""

    def __init__(self, delay: float, value: Any) -> None:
        self._delay = delay
        self._value = value

    def _respond(self) -> Any:
        time.sleep(self._delay)
        return self._value

    def read_entity_context(self, artifact_id: str) -> Any:
        return self._respond()

    def candidate_connections_for_entities(self, entity_ids: list[str]) -> Any:
        return self._respond()

    def connection_counts(self) -> Any:
        return self._respond()

    def connection_counts_for(self, entity_id: str) -> Any:
        return self._respond()

    def connection_counts_for_entities(self, entity_ids: Any) -> Any:
        return self._respond()

    def list_connections_by_types(self, types: Any) -> Any:
        return self._respond()

    def list_connections_by_types_for_entities(self, types: Any, entity_ids: Any) -> Any:
        return self._respond()

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None) -> Any:
        return self._respond()

    def find_neighbors(self, entity_id: str, *, max_hops: int = 1, conn_type: str | None = None) -> Any:
        return self._respond()

    def diagrams_referencing_type_id(self, type_id: str) -> Any:
        return self._respond()

    def search_fts(self, query: str, *, limit: int, **kwargs: bool) -> Any:
        return self._respond()


class _RaisingStore(_SlowStore):
    """Fails the test loudly if any method is ever actually called — used as the enterprise
    side for the `read_entity_context` short-circuit assertion below."""

    def _respond(self) -> Any:
        raise AssertionError("enterprise store must not be called when engagement already resolved")


# (method name, positional args, keyword args, canned empty-shape return value)
_CONCURRENT_METHODS: list[tuple[str, tuple[Any, ...], dict[str, Any], Any]] = [
    ("candidate_connections_for_entities", (["E@1.a.a"],), {}, []),
    ("connection_counts", (), {}, {}),
    ("connection_counts_for", ("E@1.a.a",), {}, (0, 0, 0)),
    ("connection_counts_for_entities", (["E@1.a.a"],), {}, {}),
    ("list_connections_by_types", (frozenset({"archimate-association"}),), {}, []),
    ("list_connections_by_types_for_entities", (frozenset({"archimate-association"}), ["E@1.a.a"]), {}, []),
    ("find_connections_for", ("E@1.a.a",), {}, []),
    ("find_neighbors", ("E@1.a.a",), {"max_hops": 1}, {}),
    ("diagrams_referencing_type_id", ("DAT@1.t.t",), {}, []),
    ("search_fts", ("query",), {"limit": 5}, []),
]


@pytest.mark.parametrize("method_name,args,kwargs,value", _CONCURRENT_METHODS)
def test_sqlite_backed_methods_dispatch_concurrently(
    method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any], value: Any
) -> None:
    engagement = cast(ReadableArtifactStore, _SlowStore(_DELAY, value))
    enterprise = cast(ReadableArtifactStore, _SlowStore(_DELAY, value))
    combined = CombinedArtifactView(engagement, enterprise)

    start = time.monotonic()
    getattr(combined, method_name)(*args, **kwargs)
    elapsed = time.monotonic() - start

    assert elapsed < _SEQUENTIAL_THRESHOLD, (
        f"{method_name} took {elapsed:.3f}s for two {_DELAY}s calls — looks sequential, not concurrent"
    )


def test_read_entity_context_short_circuits_without_touching_the_enterprise_side() -> None:
    engagement = cast(ReadableArtifactStore, _SlowStore(_DELAY, {"artifact_id": "E@1.a.a"}))
    enterprise = cast(ReadableArtifactStore, _RaisingStore(_DELAY, None))
    combined = CombinedArtifactView(engagement, enterprise)

    start = time.monotonic()
    result = combined.read_entity_context("E@1.a.a")
    elapsed = time.monotonic() - start

    assert result == {"artifact_id": "E@1.a.a"}
    assert elapsed < _SEQUENTIAL_THRESHOLD


def test_dispatch_both_routes_through_the_shared_module_level_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    assert support.EXECUTOR._max_workers == 4  # sized small — fan-out is always exactly 2 calls

    calls = []
    original_submit = support.EXECUTOR.submit

    def spy_submit(fn: Any, *args: Any) -> Any:
        calls.append(1)
        return original_submit(fn, *args)

    monkeypatch.setattr(support.EXECUTOR, "submit", spy_submit)
    support.dispatch_both(lambda x: x * 2, 3, 4)

    assert len(calls) == 2  # both sides submitted to the *same*, already-existing executor
