"""Every response model permitted to carry fields this surface does not declare, named one by one.

A closed model is the default and the point: an open one publishes `additionalProperties: true`, which
documents "an object" and promises nothing — the state of 69 of 161 operations before 0.2.0.

**The roster names concrete models, not base classes.** Inheritance was the first design and it was too
weak: `AssuranceNodeRecord` and `AffectedEntity` were open by inheriting `_FeedShaped`, and neither is
an external-feed row — an assurance node is this system's own aggregate. Nothing counted, so a model
became open by attaching whichever base was nearest, and the reason recorded in that base's docstring
was simply wrong. A roster keyed by model makes each exception cost one visible line with a reason
beside it, and `tests/architecture/test_open_response_models.py` holds the two in exact correspondence.

Reasons are not interchangeable. Two are *decisions* — the schema belongs to someone else, and mirroring
it here would drop whatever they added since the last mirror. Two are *temporary*, tracked against the
work that will remove them, and a test fails when that work finishes and the entry is still here.
"""

from __future__ import annotations

from typing import Literal

OpenReason = Literal["module-owned", "feed-owned", "pending-decision", "awaiting-contract"]

#: The schema belongs to a **diagram-type module**. Placement data for a bowtie is not shaped like a C4
#: container's, and enumerating both here would make the ontology's extensibility depend on this
#: package: adding a field to a module would mean editing a delivery DTO, and forgetting to would drop
#: the field in transit.
MODULE_OWNED: OpenReason = "module-owned"

#: The schema belongs to an **external security feed** — SBOM components, vulnerability findings, VEX
#: revisions. Findings are evidence, and dropping a field from evidence in transit is worse than
#: passing an undeclared one.
FEED_OWNED: OpenReason = "feed-owned"

#: Awaiting a **maintainer decision** recorded beside the entry. Open until then rather than closed to a
#: shape nobody has agreed, because guessing the closed form would put an invented contract in the
#: published document.
PENDING_DECISION: OpenReason = "pending-decision"

#: The **migration placeholder**: an operation whose response has not been derived from its producer
#: yet. Tracked operation-by-operation in `route_policy._response_contracts`.
AWAITING_CONTRACT: OpenReason = "awaiting-contract"

#: The complete roster. A served model with `extra="allow"` that is absent here is a contract nobody
#: agreed to; an entry here that nothing serves is a standing exception for something that no longer
#: exists, which is how the next one gets waved through.
OPEN_RESPONSE_MODELS: dict[str, OpenReason] = {
    # ── The diagram-type modules own these shapes ─────────────────────────────
    "DiagramEntityItem": MODULE_OWNED,
    "DiagramConnectionItem": MODULE_OWNED,
    "DiagramTypeMemberItem": MODULE_OWNED,

    # ── The security feeds own these ──────────────────────────────────────────
    "SecurityComponentRecord": FEED_OWNED,
    "SecurityFindingRecord": FEED_OWNED,
    "VexRevisionRecord": FEED_OWNED,
    # A snapshot is the feed's own ingest artifact: its fields are whatever the scanner recorded.
    "SnapshotRecord": FEED_OWNED,

    # ── Open pending a decision, not because anyone decided they should be ────
    #
    # `AssuranceNodeRecord` is the store's node row. Its open part is `attributes_json`, which the
    # store keeps as a `TEXT` column (`assurance/_schema.py:85`) and passes through unparsed, so the
    # wire carries a JSON *string* and the client parses it a second time
    # (`AssuranceGrcWizard.helpers.ts:61`). Closing the model means deciding whether the server parses
    # it — a wire break — or mirrors the string faithfully. Until that is decided, an invented closed
    # shape would be worse than a declared open one.
    "AssuranceNodeRecord": PENDING_DECISION,
    # `AffectedEntity` reports which architecture elements a vulnerability reaches. Its fields come
    # from this system's own impact analysis, not from a feed, so `feed-owned` was never true of it —
    # it is closeable, and the shape simply has not been derived from the producer yet.
    "AffectedEntity": PENDING_DECISION,

    # ── The drain ─────────────────────────────────────────────────────────────
    "OpenMapResponse": AWAITING_CONTRACT,
}
