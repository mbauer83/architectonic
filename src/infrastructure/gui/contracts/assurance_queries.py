"""Response contracts for the assurance store's aggregate reads: stats, coverage, risk, verification.

Derived from ``application.assurance_queries`` and ``AssuranceExposurePolicy.redact_stats``, which are
what the handlers serialise. Its own module because ``assurance_signals`` is at the module-size limit
and describes a different surface — security feeds anchored to architecture artifacts, not aggregates
over the assurance graph.

Every one of these is computed from an **exposure-filtered** node and edge set, so every count here is
"as many as this reader may see". That is a deliberate property rather than an implementation detail:
a total taken before filtering would disclose the existence of what the ceiling withholds, through a
number nobody thinks of as content. ``visibility_limited`` says when the filtering bit.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.infrastructure.gui.contracts.assurance_analyses import AssuranceAnalysisSummary


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssuranceNodeRef(_Closed):
    """A node named just enough to render a row and link to it.

    Name as well as id, because every consumer of these lists renders the name, and resolving one
    request per row against a store that already had the name in hand is the shape this avoids.
    """

    node_id: str
    name: str


class AssuranceStatsResponse(_Closed):
    """How much of the graph this reader can see, by node type.

    ``by_type`` is an open map by necessity: its keys are the node types the *ontology module* declares,
    so enumerating them here would put that vocabulary in a second place and drop any type added to the
    module but not mirrored. The envelope is closed, which is where the contract is.
    """

    node_count: int
    edge_count: int
    by_type: dict[str, int]


class AssuranceCoverageGaps(_Closed):
    """The gap categories, each naming the nodes that fall into it.

    Eight named fields rather than a map keyed by category: the producer builds exactly these, and a
    caller rendering a coverage report needs to know which categories exist without waiting to see
    whether one appears in a response. A ninth category is then a contract change, which is correct —
    it is a new thing to report.
    """

    constraints_without_evidence: list[AssuranceNodeRef]
    hazards_without_constraints: list[AssuranceNodeRef]
    obligations_without_constraints: list[AssuranceNodeRef]
    risks_without_treatment: list[AssuranceNodeRef]
    unbound_pending_csns: list[AssuranceNodeRef]
    orphan_corrective_actions: list[AssuranceNodeRef]
    failure_modes_without_an_effect: list[AssuranceNodeRef]
    failure_modes_without_a_detection_control: list[AssuranceNodeRef]


class AssuranceCoverageResponse(_Closed):
    """Where the analysis is incomplete.

    ``summary`` is prose the server composes so every surface phrases it identically — a GUI banner, a
    CLI line and an MCP tool result that each wrote their own would drift, and this sentence is the one
    a reader quotes.
    """

    total_gaps: int
    gaps: AssuranceCoverageGaps
    summary: str


class AssuranceRiskRow(_Closed):
    """One risk, with its assessment, its treatment and who owns it.

    The scoring fields are strings rather than numbers because they are *authored* values read out of
    the node's attributes, and an unset one is the empty string. Parsing them here would turn "not yet
    assessed" into zero, which reads as "assessed, and harmless".
    """

    node_id: str
    name: str
    status: str
    treatment: str
    likelihood: str
    impact: str
    risk_score: str
    #: What this risk is an assessment *of*.
    assesses: list[AssuranceNodeRef]
    #: The constraints or actions treating it.
    treated_by: list[AssuranceNodeRef]
    #: Who is accountable — the inbound side of the relation, so a risk cannot claim an owner that
    #: does not claim it.
    owners: list[AssuranceNodeRef]


class AssuranceRiskRegisterResponse(_Closed):
    """Every risk this reader may see, in a form a register renders directly."""

    risks: list[AssuranceRiskRow]
    count: int


class AssuranceVerificationIssue(_Closed):
    """One finding from the structural checks, in the form ``AssuranceIssue`` serialises to.

    ``witness`` and ``subject_name`` are always present, empty where the finding's source cannot supply
    them — the producer says why: a reader must not have to tell "nothing to show" from "this response
    predates the field".
    """

    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    #: The assurance node the finding is about; empty when the subject is the store itself.
    node_id: str
    #: The facts the finding rests on, so a claim about the graph is checkable rather than asserted.
    witness: list[str]
    #: The subject's reader-facing name; empty when the architecture model cannot name it.
    subject_name: str


class AssuranceVerifyResponse(_Closed):
    """The structural verification, as far as this reader may see.

    Every field describes the *visible* subgraph. The issues are filtered by exposure first and the
    counts and ``valid`` are then derived from what survived, so the response cannot disclose through a
    number what it withheld from the list, nor claim ``valid: false`` with no visible error to point at.
    ``visibility_limited`` is how a reader knows the answer is partial.
    """

    #: No visible error. Under a ceiling this is "nothing wrong that you may see", which is why it
    #: never travels without ``visibility_limited``.
    valid: bool
    error_count: int
    warning_count: int
    info_count: int
    issues: list[AssuranceVerificationIssue]
    #: True when the reader's ceiling is below the store's maximum, so something may be withheld.
    visibility_limited: bool


class AssuranceSearchHit(_Closed):
    """One node matched by a store-wide search, in the same envelope the architecture search uses.

    Mirrors ``_assurance_read._assurance_hit``, which builds every key explicitly rather than passing
    a stored row through — which is why this closes without the record projection the analysis and
    group collections needed.

    No content snippet, and ``path`` is always empty. Both are deliberate: a snippet may carry
    classified text, and an assurance node has no file to point at, but the field stays so one search
    surface can render architecture and assurance hits with one component. ``score`` is a constant
    1.0 — the store's search has no relevance model, and reporting a varying score it did not compute
    would be a fiction the caller might sort by.

    ``analysis`` is the authoring analysis, resolved against what this reader may see: a node whose
    analysis is above the ceiling reports none rather than naming it.
    """

    score: float
    record_type: Literal["assurance-node"]
    artifact_id: str
    name: str
    artifact_type: str
    status: str
    path: str
    analysis: AssuranceAnalysisSummary | None


class AssuranceSearchResponse(_Closed):
    """The hits, and the query they answer.

    ``count`` is the length of ``hits`` after exposure filtering, and the filter runs before the limit
    is applied — so a reader never learns that a match existed above their ceiling by finding a short
    page where they asked for twenty.
    """

    query: str
    hits: list[AssuranceSearchHit]
    count: int


class AssuranceBaselineRecord(_Closed):
    """One sealed baseline: the audit-log entry it was taken at, and the hash that fixes it.

    ``head_seq`` and ``head_hash`` are the seal. A baseline is a claim that the log up to that
    sequence hashed to that value, so publishing both is what lets anyone re-verify it later without
    trusting this system's own word — which is the only reason a baseline is worth having.

    ``analysis_id`` is null for a store-wide seal: baselining the whole log is a different act from
    baselining one analysis's work, and defaulting it to something would misreport which was done.
    """

    baseline_id: str
    created_at: str
    head_seq: int
    head_hash: str
    notes: str
    analysis_id: str | None


class AssuranceBaselineListResponse(_Closed):
    """Every baseline, newest first."""

    baselines: list[AssuranceBaselineRecord]
    count: int


class AssuranceBaselineSealedResponse(_Closed):
    """What sealing produced. No ``notes`` and no ``analysis_id``: they were the caller's own input,
    and echoing a request back as though it were a result is how a client comes to trust that the
    server agreed with something it never checked."""

    baseline_id: str
    created_at: str
    head_seq: int
    head_hash: str


class AssuranceArchRefRegisteredResponse(_Closed):
    """The reference as it was stored, which is not always as it was sent.

    ``arch_artifact_id`` comes back canonicalised: callers legitimately hold either the full or the
    short form of an artifact id, and every surface that joins on this column matches by string
    equality — so a control-structure node bound by one form and a failure mode bound by the other
    would describe the same element and never meet. Echoing the request instead of the stored key
    would hide that the two differ.
    """

    assurance_node_id: str
    arch_artifact_id: str
    ref_type: str
    status: Literal["registered"]
    verification_findings: list[dict[str, Any]] | None = None


class AssuranceCompletenessCheck(_Closed):
    """One completeness check: whether it passed, and what it found if not.

    ``gap_count`` accompanies ``gaps`` because a caller rendering a summary needs the number without
    walking the list, and the two coming from one place is what keeps them agreeing.

    Shared by every method's report and by the argument-completeness pass, because the shape genuinely
    is one shape — ``_check`` is written identically in ``stpa_complete``, ``grc_complete``,
    ``cast_complete`` and ``case_draft``. Four DTOs for it would be four things to keep in step.
    """

    passed: bool
    gap_count: int
    gaps: list[AssuranceNodeRef]


class AssuranceCompletenessReport(_Closed):
    """A set of completeness checks with a sentence a person can read.

    ``checks`` is an open map with a closed value: the check *set* belongs to the method's rules, so
    adding a check should not mean editing a delivery DTO — and the key is what a client renders as the
    check's name.
    """

    passed: bool
    checks: dict[str, AssuranceCompletenessCheck]
    summary: str


class AssuranceAnalysisCompletenessResponse(_Closed):
    """The completeness report for one analysis, for the method the analysis itself declares.

    Four endpoints used to answer this, each taking the analysis as an *optional* query parameter — so
    a caller could ask for a CAST report about an STPA analysis and receive an empty one that read like
    a clean bill of health. The server reads the method rather than letting the URL assert it, and the
    response names the method it answered for.

    ``baseline_count`` and ``incident_count`` are CAST's alone: reproducibility requires a sealed
    baseline (§10), so its report counts what it found. They are null for the other methods rather than
    zero — "not part of this method's report" and "none found" are different claims, and ``method`` is
    what a client branches on to know which it is reading.

    ``case`` is the argument-completeness pass, which runs over an analysis of any method: the GSN
    argument is a second view of the same analysis rather than a second resource, so its report travels
    with this one instead of at an address of its own.

    An analysis whose method defines no completeness report — FMEA, whose projection is its matrix —
    answers a typed 409 rather than an empty report.
    """

    analysis_id: str
    method: Literal["STPA", "CAST", "GRC"]
    passed: bool
    checks: dict[str, AssuranceCompletenessCheck]
    summary: str
    baseline_count: int | None = None
    incident_count: int | None = None
    case: AssuranceCompletenessReport
    visibility_limited: bool
