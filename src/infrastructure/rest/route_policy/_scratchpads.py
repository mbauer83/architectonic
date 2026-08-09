"""Canonical route policy for the scratchpad surface.

Identity in the path, filters in the query (ADR@1785451831): a scratchpad is addressed by its
artifact id, and `group` and `status` narrow the collection rather than naming a resource.

The resource **is the aggregate**, on purpose. There is no route for a note and none for a link,
because the root enforces the invariants and a partial update cannot be validated without loading
the whole thing anyway — one shape also removes the class of bug where two partial updates
interleave into a state neither writer intended. At a few hundred notes the payload is on the order
of 100 KB, which is unremarkable beside what `/api/entities` already returns.

`PUT` is therefore a whole-aggregate replace carrying the version the writer read; a mismatch is a
409 the client resolves by reloading. The canvas is expected to batch and debounce **in the
browser** so this endpoint sees a save and never a drag — a server-side debounce would still cost
one request per drag, and the point is that N open scratchpads must not multiply into N × events of
traffic.

**Not conditional reads.** A scratchpad changes independently of the model generation, which is the
only validator this surface has — so an ETag keyed on it would answer 304 to a client whose
scratchpad had been saved since, and a stale 304 is invisible to the client. That is the same
reason `/api/artifact-search` refuses one (`application/read_model_purity`).
"""

from __future__ import annotations

from src.infrastructure.rest.route_policy._types import BODYLESS, TYPED, RouteRow

_ID = ("artifact_id",)

SCRATCHPAD_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/scratchpads", "collection", "scratchpads_list_scratchpads", TYPED,
        cache_directive="no-cache",
    ),
    RouteRow(
        "POST", "/api/scratchpads", "collection", "scratchpads_create_scratchpad", TYPED,
        mutation_domain="repository",
    ),
    RouteRow(
        "GET", "/api/scratchpads/{artifact_id}", "detail", "scratchpads_read_scratchpad", TYPED,
        identity_parameters=_ID, cache_directive="no-cache",
    ),
    RouteRow(
        "PUT", "/api/scratchpads/{artifact_id}", "detail", "scratchpads_replace_scratchpad", TYPED,
        identity_parameters=_ID, mutation_domain="repository",
    ),
    RouteRow(
        "DELETE", "/api/scratchpads/{artifact_id}", "detail", "scratchpads_delete_scratchpad", BODYLESS,
        identity_parameters=_ID, mutation_domain="repository",
    ),
    RouteRow(
        # An `operation` row: the final segment names an act, not a stored thing. Preflight and
        # execute share it, as the write tools already do — a plan that has to be trusted twice,
        # once here and once on a second route, is a plan made against a scratchpad that may have
        # moved on in between.
        #
        # `derived-graph`, not `default`: execution goes through `artifact_bulk_write`, which stages
        # the batch and verifies the repository as a whole before committing. That is the same
        # budget diagram rendering and viewpoint execution are given, and for the same reason.
        "POST", "/api/scratchpads/{artifact_id}/lift", "operation", "scratchpads_lift_scratchpad",
        TYPED, identity_parameters=_ID, mutation_domain="repository",
        timeout_class="derived-graph",
    ),
)
