"""Which reads are a pure function of the indexed model, stated once for both transports.

A body derived only from the indexed model and its arguments cannot change while the model's
generation does not. That single judgement is what licenses both caches this system has, and the two
are *right* to be different mechanisms: REST answers a conditional GET with a 304, while MCP calls are
JSON-RPC POSTs where no conditional-GET path exists, so the same idea is applied a layer in as a
generation-keyed memo. What is not right is deciding *which reads qualify* twice.

It was decided twice. The route-policy manifest marked eight route templates ``conditional_read="etag"``
and ``install_read_cache`` held a separate frozenset of seven tool names, each with its own copy of the
rationale and its own list of standing exclusions. They had already drifted: four reads the MCP
transport treats as model-pure are not conditional on REST, and nothing related the two, so a read
reclassified on one side would keep the old answer on the other indefinitely.

**The rule.** A read qualifies when its body is a function of the indexed artifact model and the
request's own arguments, and of nothing else. The standing exclusions, once:

* **git state** — anything under ``/api/sync/`` moves with the working tree and the remote.
* **the confidential store** — anything under ``/api/assurance/`` moves with the store, which the
  model generation does not describe.
* **the clock** — a body containing a timestamp of its own production is never re-servable.
* **repository files outside the indexed set** — viewpoint definitions and JSON schemata are reloaded
  per request; the generation says nothing about them.
* **verification** — re-running it is the point.

The table below names each underlying read once and both addresses it is served at. It is the MCP
transport's authority directly, and it is held against the route-policy manifest — which stays the
REST authority, because one row per REST operation is what the rest of that manifest rests on — by
``tests/architecture/test_read_model_purity_agreement.py``, in both directions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelPureRead:
    """One read that is a function of the model generation, and where it is served.

    ``rest_templates`` may be empty — an MCP tool need not have a REST counterpart, and vice versa —
    but a read served on both and conditional on only one has to say why in ``rest_pending``.
    """

    #: What the read answers, in words, so the table can be reviewed without opening two registries.
    what: str
    rest_templates: tuple[str, ...] = ()
    mcp_tools: tuple[str, ...] = ()
    #: Why a REST address here is not yet ``conditional_read="etag"`` though the read qualifies.
    #: Empty means every REST address listed is expected to be conditional.
    rest_pending: str = ""
    tags: frozenset[str] = field(default_factory=frozenset)


MODEL_PURE_READS: tuple[ModelPureRead, ...] = (
    ModelPureRead(
        what="Repository counts by type and domain.",
        rest_templates=("/api/stats",),
        mcp_tools=("artifact_query_stats",),
    ),
    ModelPureRead(
        what="A page of artifacts of one kind, filtered and sorted.",
        rest_templates=("/api/entities", "/api/documents", "/api/diagrams"),
        mcp_tools=("artifact_query_list_artifacts",),
    ),
    ModelPureRead(
        what="One artifact with its content.",
        rest_templates=("/api/entities/{artifact_id}",),
        mcp_tools=("artifact_query_read_artifact",),
    ),
    ModelPureRead(
        what="One entity with its resolved connections.",
        rest_templates=("/api/entities/{artifact_id}/context",),
    ),
    ModelPureRead(
        what="Connections matching the filters, both endpoints resolved.",
        rest_templates=("/api/connections",),
        mcp_tools=("artifact_query_find_connections_for",),
    ),
    ModelPureRead(
        what="The entities one diagram places.",
        rest_templates=("/api/diagrams/{artifact_id}/entities",),
    ),
    # ── Qualifying on MCP, not yet conditional on REST ─────────────────────────
    #
    # Each of these is served on both transports, memoised on one and re-derived on the other. The
    # asymmetry is recorded rather than closed here: adding `conditional_read="etag"` to a served
    # route changes the response a client receives — an ETag and `Cache-Control: no-cache` appear —
    # and that is a surface change, not a consolidation.
    ModelPureRead(
        what="One document or diagram with its content.",
        rest_templates=("/api/documents/{artifact_id}", "/api/diagrams/{artifact_id}"),
        mcp_tools=(),
        rest_pending=(
            "Served by the same `artifact_query_read_artifact` the entity read is, which is "
            "memoised; the two REST detail reads were never classified alongside the entity one."
        ),
    ),
    ModelPureRead(
        what="Keyword and reference search over the indexed artifacts.",
        rest_templates=("/api/search", "/api/artifact-search", "/api/reference-search"),
        mcp_tools=("artifact_query_search_artifacts",),
        rest_pending="Scoring is a pure function of the index; no REST search route is conditional.",
    ),
    ModelPureRead(
        what="An entity's neighbourhood, stated or derived.",
        rest_templates=("/api/entities/{artifact_id}/neighbors",),
        mcp_tools=("artifact_query_find_neighbors",),
        rest_pending="Traversal reads only the index, and the derived arm is the expensive one.",
    ),
    ModelPureRead(
        what="The datatype module's declared type catalogue.",
        rest_templates=("/api/diagram-types/datatype/types",),
        mcp_tools=("artifact_query_datatype_types",),
        rest_pending=(
            "Read from the module's own configuration rather than from the index, so the model "
            "generation may not be the right validator at all. Classify before making it conditional."
        ),
    ),
)


def cacheable_mcp_tools() -> frozenset[str]:
    """Every MCP read tool the generation-keyed memo may wrap."""
    return frozenset(tool for read in MODEL_PURE_READS for tool in read.mcp_tools)


def conditional_rest_templates() -> frozenset[str]:
    """Every REST template expected to answer a conditional GET.

    Excludes the reads whose REST side is recorded as pending: they qualify, and saying so is the
    point, but a template listed here that the manifest does not mark is a failure.
    """
    return frozenset(
        template
        for read in MODEL_PURE_READS
        if not read.rest_pending
        for template in read.rest_templates
    )


def pending_rest_templates() -> frozenset[str]:
    """REST templates that qualify and are not conditional yet, with a reason recorded."""
    return frozenset(
        template for read in MODEL_PURE_READS if read.rest_pending for template in read.rest_templates
    )
