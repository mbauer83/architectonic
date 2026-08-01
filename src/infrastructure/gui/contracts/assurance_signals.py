"""Response contracts for the security-signal surface.

Every read here is anchored to one architecture artifact, so the anchor is a path segment and these
DTOs never repeat it. Each carries the *reason* it is empty rather than an empty body a caller has
to interpret: "no co-located signals store" and "this snapshot changed mid-evaluation" are different
answers, and only one of them is worth retrying.

``visibility_limited`` and ``withheld`` are declared, not optional. Exposure filtering runs before
the count, so a caller reading a list without knowing whether anything was withheld would report a
clean posture that is merely a redacted one.

The **rows** stay open where they carry a signal feed's own schema — a CycloneDX component, an OSV
finding, a VEX revision. Those vocabularies belong to the feeds, and re-declaring them here would
make this module the place every feed change has to be mirrored, dropping unmirrored fields in
transit. The response envelopes that contain them are closed, which is where the contract is.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _FeedShaped(BaseModel):
    """A row whose fields come from a security feed's schema rather than from this surface."""

    model_config = ConfigDict(extra="allow")


class _PendingContract(BaseModel):
    """Open pending a decision recorded in ``contracts/open_models.py`` — *not* a settled exception.

    Distinct from ``_FeedShaped`` because the reason is different and the two must not be confused. Two
    models here were open by inheriting ``_FeedShaped`` while being nothing of the kind, so the reason
    on record was false of both and no review could see it. A base that says "we have not decided yet"
    cannot be mistaken for one that says "the schema is not ours to declare".
    """

    model_config = ConfigDict(extra="allow")


class SecurityComponentRecord(_FeedShaped):
    """One component of the anchor's active snapshot."""


class SecurityFindingRecord(_FeedShaped):
    """One vulnerability finding against a component of the anchor's active snapshot."""


class VexRevisionRecord(_FeedShaped):
    """One revision of a VEX assessment. Revisions are appended, never replaced."""


class SnapshotRecord(_FeedShaped):
    """One snapshot row, as the store holds it."""


class FieldRejection(_Closed):
    field: str
    message: str


class SecurityComponentListResponse(_Closed):
    components: list[SecurityComponentRecord] = []
    count: int = 0
    withheld: int = 0
    reason: str | None = None


class SecurityComponentResponse(_Closed):
    """One component, addressed by the internal id this system minted for it.

    The row carries its external identifiers — ``purl``, ``bom_ref``, ``cpe``, and the source's own
    ``source_component_id`` — as data. They identify the *package*, in vocabularies other systems
    own; ``component_id`` identifies the resource here, and is the only one of them that is a path
    segment. A caller holding only a PURL resolves it through the collection filter first.
    """

    component: SecurityComponentRecord


class SecurityFindingListResponse(_Closed):
    findings: list[SecurityFindingRecord] = []
    count: int = 0
    withheld: int = 0
    reason: str | None = None


class SecurityMetricsResponse(_Closed):
    """Aggregate posture for one anchor, or the reason there is none.

    ``availability`` is the field a client branches on: ``unavailable`` means the metrics could not
    be computed — no co-located store, or a snapshot that changed mid-evaluation — and every
    numeric field is then absent rather than zero. Zero and "not computed" are different postures
    and must not share a representation.
    """

    availability: Literal["available", "unavailable"]
    reason: str | None = None
    content_state: str | None = None
    visibility_limited: bool | None = None
    basis_snapshot_id: str | None = None
    basis_activated_at: str | None = None
    computed_classification: str | None = None
    component_count: int | None = None
    finding_total: int | None = None
    open_component_findings: dict[str, int] | None = None
    distinct_open_vulnerabilities: int | None = None
    severity_band_counts: dict[str, int] | None = None
    max_cvss_score: float | None = None
    max_severity_band: str | None = None
    applicability_unknown_count: int | None = None
    unknown_severity_finding_count: int | None = None
    suppressed_finding_count: int | None = None


class AssessedEntity(_Closed):
    """One architecture entity carrying an active snapshot, with that snapshot's sizes."""

    entity_id: str
    snapshot_id: str
    bom_component_count: int
    finding_count: int


class SecuritySignalStatsResponse(_Closed):
    """Snapshot-store aggregates, or the reason there are none."""

    reason: str | None = None
    total_snapshots: int | None = None
    active_snapshots: int | None = None
    assessed_entity_count: int | None = None
    assessed_entities: list[AssessedEntity] | None = None
    active_snapshot_bom_components: int | None = None
    active_snapshot_findings: int | None = None


class VexAssessmentListResponse(_Closed):
    revisions: list[VexRevisionRecord] = []
    count: int = 0
    visibility_limited: bool = False


class VexAssessmentResponse(_Closed):
    """The revision a recorded assessment produced. Appended, so ``revision`` always advances."""

    assessment_id: str
    revision: int
    created_at: str


class SignalIngestResponse(_Closed):
    """The outcome of an ingest, projected the same way the MCP tool projects it.

    ``status`` discriminates: ``activated`` carries the persisted counts alongside the submitted
    ones, so a caller seeing fewer findings than it sent can tell alias collapse from data loss;
    ``replayed`` names the snapshot the identical request already produced; ``invalid`` carries the
    field rejections.
    """

    status: str
    snapshot_id: str | None = None
    superseded_snapshot_id: str | None = None
    component_count: int | None = None
    finding_count: int | None = None
    submitted_component_count: int | None = None
    submitted_finding_count: int | None = None
    collapsed_finding_count: int | None = None
    stored_outcome: str | None = None
    reason: str | None = None
    message: str | None = None
    errors: list[FieldRejection] | None = None


class SecuritySnapshotDeletionResponse(_Closed):
    """What the deletion removed, or why it removed nothing.

    Carries whichever of ``snapshot_id`` / ``anchor_entity_id`` addressed the deletion, so a log of
    the response says what was destroyed without needing the request beside it.
    """

    status: str
    snapshot_id: str | None = None
    anchor_entity_id: str | None = None
    message: str | None = None
    deleted: list[SnapshotRecord] = []
    deleted_count: int = 0


class AffectedEntity(_PendingContract):
    """One entity a vulnerability reaches, with the finding rows that reach it.

    Open only because the shape has not been derived from the impact-analysis producer yet. The fields
    are this system's own, so unlike a feed row this one is closeable.
    """


class VulnerabilityImpactResponse(_Closed):
    """Every visible entity affected by one vulnerability, by any of its aliases.

    ``found`` is false for an identifier no active snapshot mentions — which is not the same as one
    that affects nothing, and the two must not answer alike.
    """

    status: str | None = None
    found: bool | None = None
    affected: list[AffectedEntity] = []
    reason: str | None = None
    notes: list[str] | None = None
    canonical_id: str | None = None
    aliases: list[str] | None = None
    affected_entity_count: int | None = None
    open_entity_count: int | None = None
    max_severity_band: str | None = None
    max_cvss_score: float | None = None
    withheld_count: int | None = None


class SignalAnchorTypeListResponse(_Closed):
    """The admissible anchor types, so a client never redeclares the vocabulary."""

    anchor_types: list[str]


class AssuranceNodeRecord(_Closed):
    """One assurance node, as every backend now hands it back.

    Was open, on the reading that its ``attributes_json`` needed a decision first. It did not: the
    store keeps that column as ``TEXT`` and passes it through unparsed, so the wire carries a JSON
    *string* and the client parses it a second time (``AssuranceGrcWizard.helpers.ts``). A string is a
    ``str``. What actually blocked closing this was that the record had no single shape — nineteen
    columns from SQLCipher, seventeen from the file stores, seventeen plus collection metadata from
    PocketBase — and it is projected at the store boundary now
    (``assurance/_node_records.NODE_RECORD_FIELDS``).

    The nullable fields are the discriminated ones: a hazard has no ``uca_type``, a failure mode no
    ``concern_class``, and a legacy-invalid node no ``analysis_id`` at all — which is the state the
    provenance repair surface exists to fix, so it has to be representable rather than defaulted.
    """

    node_id: str
    node_type: str
    name: str
    status: str
    tlp: str
    concern_class: str | None
    disposition: str | None
    uca_type: str | None
    failure_type: str | None
    mode: str | None
    binding_status: str | None
    node_role: str | None
    analysis_id: str | None
    # The store's own column, passed through unparsed. Not `dict[str, Any]`: parsing it here would be
    # a wire break, and declaring it as an object while sending a string would be a false schema.
    attributes_json: str
    content_text: str
    created_at: str
    updated_at: str


class WorkingSetNodeItem(_Closed):
    """One node of an analysis's working set, and how the analysis relates to it.

    ``relationship`` is stated per item rather than left to the caller to derive by intersecting two
    lists: a borrowed node has to look borrowed, and a reader of a combined analysis who loses that
    distinction reads another method's findings as this one's.
    """

    node: AssuranceNodeRecord
    relationship: Literal["authored", "referenced"]


class AnalysisNodePageResponse(_Closed):
    """One page of the working set, with the role totals of the visible population.

    The totals describe the analysis, not the page — a caller showing "12 authored, 3 borrowed"
    would otherwise watch the numbers change as it scrolled. ``next_cursor`` is null on the last
    page; it is opaque, and the only thing to do with it is hand it back.

    ``next_cursor`` carries no default deliberately: the house pagination convention is
    ``{"items": [...], "next_cursor": null}``, so the key is *always* present and a default would
    publish it as possibly-absent — which is a different contract, and the one the client's
    ``Schema.NullOr`` would then reject on the last page.
    """

    items: list[WorkingSetNodeItem]
    next_cursor: str | None
    authored_total: int
    referenced_total: int
    visibility_limited: bool = False


class ArchLensResponse(_Closed):
    """The assurance findings that concern one architecture artifact.

    ``locked`` rather than a 423: this read is embedded in an entity view that must render whether
    or not the confidential store is open, and a locked store is a legitimate empty answer here —
    the caller needs to tell "locked" from "nothing found", which a refusal cannot express.
    """

    arch_artifact_id: str
    locked: bool
    nodes: list[AssuranceNodeRecord] = []
    count: int = 0
    visibility_limited: bool | None = None
    failure_mode_summary: dict[str, Any] | None = None


class GsnSourceBinding(_Closed):
    """One assurance node bound to one node of a published GSN diagram."""

    assurance_node_id: str
    gsn_node_id: str


class GsnPublication(_Closed):
    """One GSN diagram this analysis has been published to.

    ``binding_count`` is the number of bindings *in this list*, not the number recorded: the read
    filters by exposure before grouping, so a reader who may see two of five bound nodes is told two.
    Reporting five would disclose the existence of three nodes they cannot see, and the count is the
    obvious place for that to leak.
    """

    diagram_id: str
    binding_count: int
    source_bindings: list[GsnSourceBinding]


class GsnPublicationListResponse(_Closed):
    """Every GSN publication of one analysis.

    Derived from the ``gsn-source`` arch-refs that recording leaves behind rather than from a
    publications table — there is one fact, so recording and reading back cannot disagree. A diagram
    with no bindings the reader may see is absent rather than listed with a count of zero.
    """

    publications: list[GsnPublication]
    visibility_limited: bool = False


class AssuranceNodeCreatedResponse(_Closed):
    """The node a create produced, identified and named.

    Not the node record: a create answers with what it made, and a caller that wants the whole record
    reads it at the node's own address. Echoing the full record here would make every create pay for a
    read nobody asked for, and would put the node vocabulary in two places.

    ``verification_findings`` is present only when the write produced findings — an empty list and an
    absent key are the same news, and the absent one does not invite a caller to render "0 findings".
    """

    node_id: str
    node_type: str
    name: str
    verification_findings: list[dict[str, Any]] | None = None


class AssuranceNodeUpdatedResponse(_Closed):
    """Which fields an edit actually changed.

    ``updated`` is the fields the store wrote, not the fields the request offered: an edit that sends
    a value identical to the stored one changes nothing, and a caller invalidating caches or writing
    an audit line needs to know which it was.
    """

    node_id: str
    updated: list[str]
    verification_findings: list[dict[str, Any]] | None = None
