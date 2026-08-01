"""Which reads are a pure function of the indexed model, stated once for both transports.

A body derived only from the indexed model and its arguments cannot change while the model's
generation does not. That single judgement is what licenses both caches this system has, and the two
are *right* to be different mechanisms: REST answers a conditional GET with a 304, while MCP calls are
JSON-RPC POSTs where no conditional-GET path exists, so the same idea is applied a layer in as a
generation-keyed memo. What is not right is deciding *which reads qualify* twice.

It was decided twice. The route-policy manifest marked eight route templates ``conditional_read="etag"``
and ``install_read_cache`` held a separate frozenset of seven tool names, each with its own copy of the
rationale and its own list of standing exclusions. They had drifted, and relating them settled four
questions neither registry could ask on its own:

* three reads the MCP memo treated as pure were re-derived per request on REST, and are conditional now
  — both non-entity detail reads and the neighbourhood traversal, whose derived arm is the expensive one;
* two search routes qualify and are conditional now, and a third that *looks* like them does not:
  ``/api/artifact-search`` merges assurance-store hits, which the model generation does not describe;
* the datatype type catalogue qualifies on neither transport — it is read from module configuration
  rather than the index — and was memoised on MCP against a validator that could not see it.

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
    #: Empty means every REST address listed is expected to be conditional. Nothing is pending as of
    #: 0.2.0; the field stays because the *next* qualifying read will be found before it is marked,
    #: and recording that beats leaving it undeclared.
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
        rest_templates=(
            "/api/entities/{artifact_id}",
            "/api/documents/{artifact_id}",
            "/api/diagrams/{artifact_id}",
        ),
        mcp_tools=("artifact_query_read_artifact",),
    ),
    ModelPureRead(
        what="Keyword and reference search over the indexed artifacts.",
        rest_templates=("/api/search", "/api/reference-search"),
        mcp_tools=("artifact_query_search_artifacts",),
    ),
    ModelPureRead(
        what="An entity's neighbourhood, stated or derived.",
        rest_templates=("/api/entities/{artifact_id}/neighbors",),
        mcp_tools=("artifact_query_find_neighbors",),
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
    # ── Refused, with the reason ───────────────────────────────────────────────
    #
    # `/api/artifact-search` looks like the two searches above and is not one of them: it merges
    # assurance-store hits into its result (`entities/search.py:110`). The store moves independently
    # of the model, so a 304 keyed on the model generation would hide a node ingested since — and a
    # stale 304 is invisible to the client. The MCP `artifact_query_search_artifacts` searches only
    # the index, which is why it stays above while this route stays out.
    #
    # `/api/diagram-types/datatype/types` and its `artifact_query_datatype_types` tool read the
    # datatype module's own `config.yaml`, not the index. The model generation says nothing about
    # module configuration, so it is the wrong validator in both directions — the tool was memoised
    # against it until 0.2.0, which is a defect rather than an optimisation, and neither is here now.
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
