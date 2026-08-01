"""Every response model permitted to carry fields this surface does not declare, named one by one.

A closed model is the default and the point: an open one publishes `additionalProperties: true`, which
documents "an object" and promises nothing — the state of 69 of 161 operations before 0.2.0.

**The roster names concrete models, not base classes.** Inheritance was the first design and it was too
weak: `AssuranceNodeRecord` and `AffectedEntity` were open by inheriting `_FeedShaped`, and neither is
an external-feed row — an assurance node is this system's own aggregate. Nothing counted, so a model
became open by attaching whichever base was nearest, and the reason recorded in that base's docstring
was simply wrong. A roster keyed by model makes each exception cost one visible line with a reason
beside it, and `tests/architecture/test_open_response_models.py` holds the two in exact correspondence.

Reasons are not interchangeable. Some are *decisions* — the schema belongs to someone else, and mirroring
it here would drop whatever they added since the last mirror. Two are *temporary*, tracked against the
work that will remove them, and a test fails when that work finishes and the entry is still here.

**There are two rosters, because there are two ways to publish an arbitrary object.** A model with
`extra="allow"` is the visible one. The other is a *field* typed `dict[str, Any]`: the model around it
forbids extras, its docstring says "closed", and the schema it publishes says `additionalProperties:
true` for that property. `WriteResultResponse.verification` was one, on every mutation the surface
serves, and the roster keyed by model could not see it — the check read `model_config["extra"]`, which
is silent about field types. `OPEN_RESPONSE_FIELDS` names those, keyed `Model.field`, and the check now
reads the *published schema* so neither form can hide.
"""

from __future__ import annotations

from typing import Literal

OpenReason = Literal[
    "module-owned",
    "feed-owned",
    "authored",
    "rule-owned",
    "foreign-vocabulary",
    "pending-decision",
    "awaiting-contract",
]

#: The schema belongs to a **diagram-type module**. Placement data for a bowtie is not shaped like a C4
#: container's, and enumerating both here would make the ontology's extensibility depend on this
#: package: adding a field to a module would mean editing a delivery DTO, and forgetting to would drop
#: the field in transit.
MODULE_OWNED: OpenReason = "module-owned"

#: The schema belongs to an **external security feed** — SBOM components, vulnerability findings, VEX
#: revisions. Findings are evidence, and dropping a field from evidence in transit is worse than
#: passing an undeclared one.
FEED_OWNED: OpenReason = "feed-owned"

#: The keys are the **artifact's own authored data** — its type's attribute schema decides them, or
#: nothing does and the repository round-trips unmodelled frontmatter verbatim. Declaring them here
#: would mean this package deciding what an entity may say about itself.
AUTHORED: OpenReason = "authored"

#: The keys are written by the **verification rule** that raised the finding, and rules live in the core
#: verifier and in diagram-type modules alike — the datatype module's unresolved-type-reference finding
#: carries `classifier`/`candidates`, the workspace-identity rule carries `committed_host`. Enumerating
#: them would make a module's findings depend on this package to reach a client.
RULE_OWNED: OpenReason = "rule-owned"

#: The value's vocabulary belongs to an **external specification** — a JSON Schema document, say. Its
#: keywords are that specification's, so mirroring them here would make this package a second, lagging
#: definition of something already defined.
FOREIGN_VOCABULARY: OpenReason = "foreign-vocabulary"

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
    # `AffectedEntity` reports which architecture elements a vulnerability reaches. Its fields come
    # from this system's own impact analysis, not from a feed, so `feed-owned` was never true of it —
    # it is closeable, and the shape simply has not been derived from the producer yet.
    "AffectedEntity": PENDING_DECISION,

    # ── The drain ─────────────────────────────────────────────────────────────
    "OpenMapResponse": AWAITING_CONTRACT,
}

#: Every *field* of a closed model whose type publishes `additionalProperties: true` — the other way an
#: arbitrary object reaches a client, and the way that stayed invisible until `verification` was found on
#: every mutation response. Keyed `Model.field`, exactly as
#: `tests/architecture/test_open_response_models.py` reports it from the published schema.
#:
#: An `awaiting-contract` entry here is a field whose closed shape is already legible from its producer,
#: named beside the entry, and left for the slice that owns that surface. They cannot be forgotten: the
#: same test that retires the model-level drain requires this roster to hold nothing temporary once the
#: operation ledger empties, so "every operation typed" cannot be reached while an operation's response
#: still contains an object nobody described.
OPEN_RESPONSE_FIELDS: dict[str, OpenReason] = {
    # ── The artifact's own data ───────────────────────────────────────────────
    # `attributes`/`properties` keys come from the entity type's attribute schema and their value types
    # from each attribute's declared type; `extra` and `metadata` are frontmatter this system does not
    # model and returns as written.
    "EntityDetailResponse.attributes": AUTHORED,
    "EntityDetailResponse.properties": AUTHORED,
    "EntityDetailResponse.extra": AUTHORED,
    "DocumentDetailResponse.extra": AUTHORED,
    "ConnectionSummary.metadata": AUTHORED,

    # ── A diagram-type module owns the shape ──────────────────────────────────
    "EntityDetailResponse.display_blocks": MODULE_OWNED,

    # ── The rule that raised the finding owns the shape ───────────────────────
    "VerificationIssueResponse.details": RULE_OWNED,
    "VerificationIssueResponse.actions": RULE_OWNED,

    # ── Someone else's vocabulary ─────────────────────────────────────────────
    # A JSON Schema document, served so an authoring form validates against exactly what the verifier
    # validates against. Mirroring the meta-schema here would be this package's second-hand copy of it.
    "EntitySchemaResponse.schema": FOREIGN_VOCABULARY,

    # ── The drain, field by field ─────────────────────────────────────────────
    # `attribute_descriptors` (`application/artifact_schema.py:310`) builds each descriptor here, from a
    # fixed set of keys: `type`, and optionally `enum`, `default`, `constraints`, `items`. Ours to close,
    # with the entity surface.
    "EntitySchemaResponse.descriptors": AWAITING_CONTRACT,
    # `assurance_fmea_lens.failure_mode_summary` returns exactly `worst_action_priority`, `high_count`,
    # `unanswered_cells`, `nominated_by`. Closes with the assurance surface.
    "ArchLensResponse.failure_mode_summary": AWAITING_CONTRACT,
    # The post-write assurance verify's findings, as `assurance_mutations.MutationOk.findings` carries
    # them. Closes with the assurance surface.
    "AssuranceNodeCreatedResponse.verification_findings": AWAITING_CONTRACT,
    "AssuranceNodeUpdatedResponse.verification_findings": AWAITING_CONTRACT,
    # The viewpoint a diagram projects. Its definition language is determinate — the GUI editor already
    # enumerates every node kind to round-trip an edit — so this closes with the viewpoint surface.
    "DiagramSummary.viewpoint": AWAITING_CONTRACT,
}
