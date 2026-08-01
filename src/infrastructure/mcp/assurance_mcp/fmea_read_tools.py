"""The failure-mode matrix, for an agent conducting the analysis.

`assurance_read_node` reports one failure mode's factors, which is enough to record a judgement about
a row already known. It is not enough to *run* the method, and the two gaps are the ones the method
exists to close:

* **Which rows exist.** The candidate set is a nomination — the elements a control structure already
  names, plus the ones the architecture graph shows to be load-bearing. The second half is computed
  from declared relationship roles and strengths in the architecture repository, so it cannot be
  reconstructed from the assurance store at all.
* **Which cells nobody has examined.** `assurance_verify` reports an element with *no* failure modes
  (W510) and is silenced by the first one recorded, so an element with one guideword of five
  examined produces no finding anywhere. Coverage is the question, and it was invisible.

Same use case as the REST surface the GUI reads, so the grid an agent sees and the grid a person sees
cannot disagree.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.application.assurance.fmea_rows import matrix_rows
from src.domain.assurance.fmea_factors import FactorAssessment
from src.infrastructure.assurance.architecture_basis import current_architecture_basis
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context

FAILURE_MODE = "failure-mode"


def register_fmea_read_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_fmea_matrix",
        description=(
            "The failure-mode matrix: candidate elements crossed with the five failure guidewords. "
            "Each row names the element, why it was nominated (control-structure and/or "
            "load-bearing), how many cells are answered and unanswered, and its worst action "
            "priority. Each cell reports its state — recorded, not-credible, or untouched — its "
            "action priority, each factor with the basis it came from and the basis_digest to "
            "record a judgement against, whether an occurrence is being asked for at all, and the "
            "single next action that would advance it. A cell dismissed as not credible carries who "
            "decided and why, and counts as examined. Use this to find what is left to analyse: "
            "assurance_verify reports an element with no failure modes at all, but says nothing "
            "about an element examined against one guideword out of five. Optional analysis_id "
            "scopes which failure modes are placed into the grid; the candidate set is not scoped."
        ),
    )
    def assurance_fmea_matrix(analysis_id: str | None = None) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        policy = AssuranceExposurePolicy(ctx.max_classification, True)
        visible_nodes, _ = policy.filter_nodes(ctx.store.list_nodes())
        visible_ids = frozenset(str(n["node_id"]) for n in visible_nodes)
        edges = policy.filter_edges(ctx.store.list_edges(), visible_ids)
        # Failure modes are scoped to the requested analysis; everything else is not. The causal
        # chain behind a row belongs to the analysis that produced it, and filtering the traversal
        # would report every matrix as incomplete.
        scoped = [
            n for n in visible_nodes
            if analysis_id is None
            or str(n.get("node_type", "")) != FAILURE_MODE
            or str(n.get("analysis_id") or "") == analysis_id
        ]
        failure_mode_ids = [
            str(n["node_id"]) for n in scoped if str(n.get("node_type", "")) == FAILURE_MODE
        ]
        stored = ctx.store.read_fmea_assessments(failure_mode_ids)
        rows = matrix_rows(
            nodes=scoped,
            edges=edges,
            arch_refs=ctx.store.list_arch_refs(),
            assessments={
                node_id: [FactorAssessment.from_row(row) for row in revisions]
                for node_id, revisions in stored.items()
            },
            basis=current_architecture_basis(),
        )
        return {"analysis_id": analysis_id, "rows": rows, "count": len(rows)}
