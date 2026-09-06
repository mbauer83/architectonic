"""A read after the index is closed fails, instead of waiting for a connection that cannot arrive.

`close()` drains the pool and keeps it drained, so a later `get()` blocked forever on a queue nothing
would ever put to again. That presented as the worst symptom a defect can have: a test stopped inside
a search, its xdist worker silent, the controller waiting on it, and the whole run hanging near the
end — no failure, no output, and once a real failure printed nowhere because the run never finished.

The pool is where the answer lives. Nothing above it can tell "busy" from "never coming back", which
is exactly what `queue.get()` cannot tell either.
"""

from __future__ import annotations

import threading

import pytest

from src.infrastructure.artifact_index._read_pool import ReadConnectionPool, ReadPoolClosed

_URI = "file:read-pool-test?mode=memory&cache=shared"


def _pool(size: int = 2) -> ReadConnectionPool:
    return ReadConnectionPool(_URI, size=size)


def test_a_reader_works_before_the_pool_is_closed() -> None:
    with _pool().reader() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1


def test_a_reader_after_close_refuses(  ) -> None:
    pool = _pool()
    pool.close()

    with pytest.raises(ReadPoolClosed):
        with pool.reader():
            pass


def test_the_refusal_says_what_to_do_about_it() -> None:
    pool = _pool()
    pool.close()

    with pytest.raises(ReadPoolClosed, match="closed and is being read again"):
        with pool.reader():
            pass


def test_the_refusal_is_prompt_rather_than_a_minute_of_waiting() -> None:
    """The guard, not the timeout, is what answers a closed pool: waiting a minute to say so would
    still stall a suite, just for less long."""
    pool = _pool()
    pool.close()
    finished = threading.Event()

    def _read() -> None:
        with pytest.raises(ReadPoolClosed), pool.reader():
            pass
        finished.set()

    threading.Thread(target=_read, daemon=True).start()

    assert finished.wait(timeout=5), "a closed pool took longer than a moment to refuse a read"


def test_a_connection_is_returned_so_the_next_reader_gets_one() -> None:
    """The property the pool exists for, pinned beside the refusal: a pool of one still serves
    every caller in turn."""
    pool = _pool(size=1)

    for _ in range(3):
        with pool.reader() as connection:
            assert connection.execute("SELECT 1").fetchone()[0] == 1


def test_close_is_idempotent() -> None:
    pool = _pool()
    pool.close()
    pool.close()

    assert pool.size() == 0
