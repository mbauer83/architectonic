"""Bounded, generation-keyed memoization for read-only MCP tool results.

Agent traffic is bursty and repetitive: a fleet of agents and subagents working the same
repository issues many parallel calls, and a large share of them ask a question someone just
asked. Every one of those re-derives an answer the process already produced. MCP calls are
JSON-RPC POSTs, so the HTTP conditional-GET path does nothing for them — the same idea has
to be applied a layer in, keyed on the same read-model generation.

Three bounds, because an unbounded memo of this data is worse than none:

* **Generation.** Every entry is stamped with the read-model generation it was produced
  under, and a lookup against a newer generation misses. Correctness never rests on eviction.
* **Entry size.** A single `artifact_query_list_artifacts` over a large repository is a
  multi-megabyte structure. Caching those would evict everything cheap and useful to hold a
  handful of expensive rarities, so anything over the cap is served but never stored.
* **Entry count.** Plain LRU over what remains, so a burst of distinct argument combinations
  cannot grow the process without limit.

Deliberately not a decorator over every tool: only tools that are pure functions of the read
model may opt in. A tool that reads git state, the assurance store, or the clock would be
memoizing something the generation does not describe.
"""

from __future__ import annotations

import json
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Entries above this serialized size are never stored. Chosen so an ordinary entity or
#: neighbourhood answer fits while a whole-repository listing does not.
MAX_ENTRY_BYTES = 256 * 1024

#: Upper bound on retained entries. With the size cap above this bounds the cache's own
#: footprint to a few tens of megabytes at worst.
MAX_ENTRIES = 256


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    stored: int
    too_large: int
    entries: int


class ReadResultCache:
    """LRU of read-tool results, valid only for the generation they were produced under."""

    def __init__(self, *, max_entries: int = MAX_ENTRIES, max_entry_bytes: int = MAX_ENTRY_BYTES) -> None:
        self._max_entries = max_entries
        self._max_entry_bytes = max_entry_bytes
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[int, Any]] = OrderedDict()
        self._hits = self._misses = self._stored = self._too_large = 0

    def _key(self, tool: str, arguments: dict[str, Any]) -> str:
        # sort_keys so argument order never produces a second entry for the same question;
        # default=str so an un-encodable argument degrades to a distinct key rather than
        # raising inside a read path.
        return f"{tool}\n{json.dumps(arguments, sort_keys=True, default=str)}"

    def get_or_compute(
        self, tool: str, arguments: dict[str, Any], generation: int | None, compute: Callable[[], Any]
    ) -> Any:
        """Return a cached result for this generation, or compute, maybe store, and return.

        A ``generation`` of None means the caller could not establish one — the answer is
        computed and never stored, because there would be nothing to invalidate it.
        """
        if generation is None:
            return compute()
        key = self._key(tool, arguments)
        with self._lock:
            found = self._entries.get(key)
            if found is not None and found[0] == generation:
                self._entries.move_to_end(key)
                self._hits += 1
                return found[1]
            self._misses += 1

        result = compute()

        if sys.getsizeof(repr(result)) > self._max_entry_bytes:
            with self._lock:
                self._too_large += 1
            return result

        with self._lock:
            self._entries[key] = (generation, result)
            self._entries.move_to_end(key)
            self._stored += 1
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return result

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._hits, misses=self._misses, stored=self._stored,
                too_large=self._too_large, entries=len(self._entries),
            )
