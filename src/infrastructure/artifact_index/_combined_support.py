from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

_T = TypeVar("_T")
_S = TypeVar("_S")
_RECORD_TYPE_ORDER = ("entity", "connection", "diagram", "document")

EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="combined-artifact-index")


def first_not_none(left: _T | None, right: Callable[[], _T | None]) -> _T | None:
    return left if left is not None else right()


def dispatch_both(fn: Callable[[_S], _T], engagement: _S, enterprise: _S) -> tuple[_T, _T]:
    """Submit `fn` against both stores to the shared executor and block for both results.

    Both tasks are submitted before either `.result()` is awaited, so the two calls run
    concurrently rather than sequentially — required for every SQLite-backed store method
    (REQ@1782080517.IIl8-4), not just search.
    """
    left = EXECUTOR.submit(fn, engagement)
    right = EXECUTOR.submit(fn, enterprise)
    return left.result(), right.result()


def merge_sorted(left: list[_T], right: list[_T], key: Callable[[_T], str]) -> list[_T]:
    out: list[_T] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if key(left[i]) <= key(right[j]):
            out.append(left[i])
            i += 1
        else:
            out.append(right[j])
            j += 1
    out.extend(left[i:])
    out.extend(right[j:])
    return out


def sum_tuple(left: tuple[int, int, int], right: tuple[int, int, int]) -> tuple[int, int, int]:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def sum_count_dicts(
    left: dict[str, tuple[int, int, int]],
    right: dict[str, tuple[int, int, int]],
) -> dict[str, tuple[int, int, int]]:
    out = dict(left)
    for key, value in right.items():
        out[key] = sum_tuple(out.get(key, (0, 0, 0)), value)
    return out


def merge_counter_dicts(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key in set(left) | set(right):
        lval = left.get(key)
        rval = right.get(key)
        if isinstance(lval, int) and isinstance(rval, int):
            out[key] = lval + rval
        elif isinstance(lval, dict) and isinstance(rval, dict):
            counts = dict(lval)
            for name, count in rval.items():
                if isinstance(count, int):
                    counts[name] = int(counts.get(name, 0)) + count
            out[key] = counts
        else:
            out[key] = lval if rval is None else rval
    return out


def merge_search_rows(
    left: list[tuple[str, str, float]],
    right: list[tuple[str, str, float]],
    *,
    limit: int,
) -> list[tuple[str, str, float]]:
    per_kind_limit = max(limit, 1)
    out: list[tuple[str, str, float]] = []
    for record_type in _RECORD_TYPE_ORDER:
        rows = [row for row in (*left, *right) if row[1] == record_type]
        out.extend(sorted(rows, key=lambda row: (-row[2], row[0]))[:per_kind_limit])
    return sorted(out, key=lambda row: (-row[2], row[0]))
