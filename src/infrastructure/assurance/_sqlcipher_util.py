"""Shared SQL plumbing for the SQLCipher assurance store adapter.

Row-factory, timestamp, parameterised WHERE-builder, and the fd-2 stderr
suppressor used during key verification. Kept separate so the store adapter
stays focused on the port surface.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

from src.domain.clock import utc_now_iso as now_iso

__all__ = ["dict_row_factory", "now_iso", "suppress_c_stderr", "where"]


def dict_row_factory(cursor: Any, row: Any) -> dict[str, object]:
    """Convert a sqlcipher3 row to a plain dict using cursor.description."""
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, row))


def where(filters: dict[str, object | None]) -> tuple[str, list[object]]:
    """Build a parameterised ``WHERE`` clause from the truthy entries of ``filters``.

    Keys are trusted column names; values become positional ``?`` parameters.
    Returns ``("", [])`` when no filter is active.
    """
    active = [(col, val) for col, val in filters.items() if val]
    clauses = " AND ".join(f"{col} = ?" for col, _ in active)
    clause = f"WHERE {clauses}" if active else ""
    return clause, [val for _, val in active]


@contextlib.contextmanager  # type: ignore[misc]
def suppress_c_stderr():  # type: ignore[return]
    """Redirect fd 2 to /dev/null for C-library calls that emit diagnostic noise.

    SQLCipher writes 'ERROR CORE ...' messages directly to fd 2 before raising a
    Python exception on key mismatch. Suppress them here; the RuntimeError raised
    by the caller carries the actionable message.
    """
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    os.dup2(devnull_fd, 2)
    try:
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull_fd)
