"""Closing an index releases its connections, and the process no longer leaks one per index.

`ArtifactIndex` had no `close()`. Its `_SqliteStore` opens a write connection plus a pool of readers
against a shared-cache in-memory database, and the only thing that ever released them was the garbage
collector — which Python reports as `ResourceWarning: unclosed database`. **433 of them** appeared the
moment `filterwarnings = ["error", …]` went into `pyproject.toml`, which is how a backlog item
("index close()") turned out to be measurable.

Two costs, and only the first is about tests. A served backend holds one database plus a reader pool
alive for as long as the process runs, per index. And under xdist the release of the underlying lock
is deferred to whenever the collector runs, which is a plausible contributor to the load-dependent
flakes this release has been chasing.

The fix is a lifecycle method at each layer that owns something: `_SqliteStore` closes the
connections, `ArtifactIndex` delegates, `CombinedArtifactView` closes both halves, and
`ArtifactIndexLifecycle` — the port that already meant "lifecycle" — declares it, so a caller holding
the facade never has to reach through to a private store. The backend's teardown names it as a step.

These tests are the ones that fail without that: the first two by raising the very `ResourceWarning`
the register exempts, the rest by `AttributeError` on a method that did not exist.
"""

from __future__ import annotations

import gc
import sqlite3
import warnings
from pathlib import Path

import pytest

from src.application.artifacts.repository import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.artifact_index.service import ArtifactIndex


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagement" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    return root


def test_a_closed_index_emits_no_unclosed_database_warning(repo: Path) -> None:
    """The regression, stated as the warning itself rather than as a proxy for it."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        index = ArtifactIndex(repo)
        index.close()
        del index
        gc.collect()


def test_an_unclosed_index_is_what_produced_the_433(repo: Path) -> None:
    """The other half of the biconditional: without `close()`, the warning is real and reproducible.

    Recorded rather than merely implied, because a test that only proves the fixed path stays green if
    someone quietly turns `close()` into a no-op.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        ArtifactIndex(repo)
        gc.collect()
    assert any("unclosed database" in str(w.message) for w in caught), [str(w.message) for w in caught]


def test_close_is_idempotent(repo: Path) -> None:
    # A context manager exiting after an explicit close is ordinary, so the second call must not raise.
    index = ArtifactIndex(repo)
    index.close()
    index.close()


def test_the_index_is_a_context_manager(repo: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        with ArtifactIndex(repo) as index:
            assert index.repo_root == repo
        gc.collect()


def test_the_write_connection_is_actually_closed(repo: Path) -> None:
    """Closed, not merely dereferenced: using it afterwards must be an error from SQLite itself."""
    index = ArtifactIndex(repo)
    connection = index._db._conn  # noqa: SLF001 - asserting the private connection is what shut
    index.close()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_every_pooled_reader_is_closed_too(repo: Path) -> None:
    """The pool is the larger half of the leak — one write connection, several readers."""
    index = ArtifactIndex(repo)
    pool = index._db._read_pool  # noqa: SLF001
    assert pool.size() > 1, "the store should open a read pool, so there is something to close"

    # Hold each connection by checking it out and returning it, so the identities survive the close.
    readers = []
    for _ in range(pool.size()):
        with pool.reader() as connection:
            readers.append(connection)

    index.close()
    for reader in readers:
        with pytest.raises(sqlite3.ProgrammingError):
            reader.execute("SELECT 1")


def test_the_repository_facade_closes_the_store_it_wraps(repo: Path) -> None:
    """The delegation the facade was missing.

    Without it, the only way to release the connections from what a caller actually holds was to reach
    through to `_store` — a different, less appropriate API for the same job, which is the shape this
    codebase rejects on principle.
    """
    index = ArtifactIndex(repo)
    repository = ArtifactRepository(index)
    repository.close()
    with pytest.raises(sqlite3.ProgrammingError):
        index._db._conn.execute("SELECT 1")  # noqa: SLF001


def test_a_combined_view_closes_both_halves(tmp_path: Path) -> None:
    """Closing the thing a caller holds must not leak the half it cannot reach."""
    engagement = tmp_path / "engagement" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    for root in (engagement, enterprise):
        (root / "model").mkdir(parents=True)

    view = combined_artifact_index(engagement, enterprise)
    halves = [view._engagement, view._enterprise]  # type: ignore[attr-defined]  # noqa: SLF001
    view.close()
    for half in halves:
        with pytest.raises(sqlite3.ProgrammingError):
            half._db._conn.execute("SELECT 1")  # noqa: SLF001


def test_the_teardown_names_closing_the_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """A served process must close it, so the obligation is declared in the teardown order.

    Asserted against the step list rather than by running a shutdown, because what matters is that the
    obligation is *named* and ordered after the write drain — a write in flight is still using the
    index it would otherwise close underneath.
    """
    from src.infrastructure.backend._teardown import teardown_steps

    names = [name for name, _ in teardown_steps(None)]
    assert "close the artifact index" in names, names
    assert names.index("drain in-flight writes") < names.index("close the artifact index"), names


def test_the_teardown_step_is_silent_when_no_repository_was_installed() -> None:
    """A backend that failed before `init_state` owes nothing here, and must not raise on the way out."""
    from src.infrastructure.backend._teardown import _close_artifact_index
    from tests.support.rest_state import reset_state_for_test

    reset_state_for_test()
    _close_artifact_index()
