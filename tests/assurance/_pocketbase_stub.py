"""Just enough PocketBase to exercise the REST assurance adapters without a server.

Shared by the backend conformance suites. One stub rather than one per suite: two fakes of the
same server drift, and the moment they do, a suite starts asserting against a server that does
not exist anywhere else.

Collections are kept apart, as the real server does. Pooling them would let a node record answer
a factor query — a property of the stub, not of the adapter, and it would mask whether the adapter
queries the right collection at all.

Records are given a server-side `id` on create, because that is what PocketBase returns and what
the adapters address a record by when they update or delete it. A stub that omitted it would let
an adapter's update path go untested precisely where it differs from its create path.
"""

from __future__ import annotations

from typing import Any


class StubResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class StubPocketBaseClient:
    """An in-memory stand-in for the authenticated PocketBase client."""

    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self._next_id = 0

    def close(self) -> None:
        return None

    def get(self, url: str, params: dict[str, object]) -> StubResponse:
        bound = {k: v for k, v in params.items() if k not in ("filter", "perPage", "sort")}
        records = self.collections.get(url, [])
        items = [r for r in records if all(str(r.get(k)) == str(v) for k, v in bound.items())]
        return StubResponse({"items": items})

    def post(self, url: str, json: dict[str, object]) -> StubResponse:
        self._next_id += 1
        record = {"id": f"pb{self._next_id}", **json}
        self.collections.setdefault(url, []).append(record)
        return StubResponse(dict(record))

    def patch(self, url: str, json: dict[str, object]) -> StubResponse:
        collection_url, record_id = url.rsplit("/", 1)
        for record in self.collections.get(collection_url, []):
            if record.get("id") == record_id:
                record.update(json)
                return StubResponse(dict(record))
        return StubResponse({})

    def delete(self, url: str) -> StubResponse:
        collection_url, record_id = url.rsplit("/", 1)
        remaining = [
            record for record in self.collections.get(collection_url, [])
            if record.get("id") != record_id
        ]
        self.collections[collection_url] = remaining
        return StubResponse({})
