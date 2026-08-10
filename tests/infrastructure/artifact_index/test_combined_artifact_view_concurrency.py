"""Guards REQ@1782080517.IIl8-4 ("Concurrent Reads, Serialized Writes") on the combined-scope
read path: every one of the eleven SQLite-backed ArtifactStorePort methods must dispatch to
both canonical instances concurrently — except `read_entity_context`, which is a fallback (only
one side is ever actually queried) and must therefore short-circuit instead.

Concurrency is asserted by **rendezvous, not by the clock**. Each canned store waits at a
`threading.Barrier(2)`: if both sides are in flight at once the barrier releases immediately, and if
they are dispatched one after the other the first waits alone until the barrier breaks. Either way
the verdict is the same on an idle machine and a loaded one.

It used to time two 0.15 s sleeps and demand the pair finish inside 0.24 s, which measures the
machine as much as the dispatch — under load a genuinely concurrent pair failed. A test that goes red
because something else is busy teaches everyone to re-run it, which is how a real regression gets
waved through.
"""

from __future__ import annotations

import threading
from typing import Any, cast

import pytest

from src.application.ports import ReadableArtifactStore
from src.infrastructure.artifact_index import _combined_support as support
from src.infrastructure.artifact_index.combined_index import CombinedArtifactView

#: How long a party waits for the other to arrive before declaring the dispatch sequential. Generous
#: on purpose: it is a deadlock ceiling, not a performance budget, so a slow machine only makes a
#: *passing* test take the same short time and a *failing* one take longer to say so.
_RENDEZVOUS_TIMEOUT = 10.0


class _SlowStore:
    """Test double: every relevant method waits for the other side, then returns `value`.

    Sharing one barrier between the two stores is what makes the assertion binary. Concurrent
    dispatch means both parties reach `wait()` and it releases at once; sequential dispatch means the
    first blocks and nothing else ever arrives, so the barrier breaks on timeout and the call raises.
    """

    def __init__(self, barrier: threading.Barrier | None, value: Any) -> None:
        self._barrier = barrier
        self._value = value

    def _respond(self) -> Any:
        if self._barrier is not None:
            self._barrier.wait()
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
    barrier = threading.Barrier(2, timeout=_RENDEZVOUS_TIMEOUT)
    engagement = cast(ReadableArtifactStore, _SlowStore(barrier, value))
    enterprise = cast(ReadableArtifactStore, _SlowStore(barrier, value))
    combined = CombinedArtifactView(engagement, enterprise)

    try:
        getattr(combined, method_name)(*args, **kwargs)
    except threading.BrokenBarrierError as broken:  # pragma: no cover — only on a real regression
        raise AssertionError(
            f"{method_name} never had both stores in flight at once: one side waited "
            f"{_RENDEZVOUS_TIMEOUT}s and the other never arrived, so it dispatches sequentially"
        ) from broken


def test_read_entity_context_short_circuits_without_touching_the_enterprise_side() -> None:
    # No barrier: this path must resolve from one side alone, and `_RaisingStore` is what proves the
    # other is never reached — a stronger statement than any elapsed time could make.
    engagement = cast(ReadableArtifactStore, _SlowStore(None, {"artifact_id": "E@1.a.a"}))
    enterprise = cast(ReadableArtifactStore, _RaisingStore(None, None))
    combined = CombinedArtifactView(engagement, enterprise)

    assert combined.read_entity_context("E@1.a.a") == {"artifact_id": "E@1.a.a"}


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
