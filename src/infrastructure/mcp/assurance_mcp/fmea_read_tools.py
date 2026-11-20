"""The failure-mode matrix, for an agent conducting the analysis.

`assurance_read_node` reports one failure mode's factors, which is enough to record a judgement about
a row already known. It is not enough to *run* the method, and the two gaps are the ones the method
exists to close:

* **Which rows exist.** The candidate set is a nomination — the elements a control structure already
  names — and it is every such element in the store, not only the ones an FMEA has reached, so it
  cannot be read off the failure modes that happen to exist.
* **Which cells nobody has examined.** `assurance_verify` reports an element with *no* failure modes
  (W510) and is silenced by the first one recorded, so an element with one guideword of five
  examined produces no finding anywhere. Coverage is the question, and it was invisible.

Same use case as the REST surface the GUI reads — `application.assurance.fmea_matrix` — so the grid an
agent sees and the grid a person sees cannot disagree, and neither can be asked for without an
analysis. What differs is the rendering: a tool result has a budget a page does not, so the default
here is the summary and the full grid is asked for by name.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.application.assurance.fmea_matrix import (
    AnalysisMatrix,
    MatrixAnalysisNotFound,
    MatrixMethodMismatch,
    matrix_of_analysis,
    summary_rows,
)
from src.domain.artifact_id import canonical_entity_key
from src.infrastructure.assurance.architecture_basis import current_architecture_basis
from src.infrastructure.mcp.assurance_mcp import _refusals
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.mcp.tool_annotations import READ_ONLY

MatrixMode = Literal["summary", "full"]


def register_fmea_read_tools(server: MCPServer) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_fmea_matrix",
        description=(
            "The failure-mode matrix of one FMEA analysis: its candidate elements crossed with the "
            "five failure guidewords. analysis_id is required — list the FMEA analyses with "
            "assurance_list_analyses(method='FMEA'); an unknown id answers not_found and an "
            "analysis of another method answers analysis_method_mismatch. Each row names the "
            "element, why it was nominated (control-structure), how many cells are answered and "
            "unanswered, and its worst action priority. mode='summary' (default): each cell "
            "reports its state — recorded, not-credible, or untouched — its node_id, its action "
            "priority, whether an occurrence is being asked for at all, and the single next action "
            "that would advance it; read a recorded cell's factors with assurance_read_node, whose "
            "factor_report carries the basis_digest to record a judgement against. mode='full': "
            "each cell also carries every factor with its basis and basis_digest, who dismissed a "
            "not-credible cell and why, and the drafted occurrence rationale, which lists every "
            "fact the architecture model holds about the element and can be very large — narrow "
            "it with element_id. element_id returns only that element's row, in either mode. Use "
            "this to find what is left to analyse: assurance_verify reports an element with no "
            "failure modes at all, but says nothing about an element examined against one "
            "guideword out of five. Only the failure modes the analysis produced are placed into "
            "the grid; the candidate set is every element a control structure names."
        ),
        annotations=READ_ONLY,
    )
    def assurance_fmea_matrix(
        analysis_id: str,
        mode: MatrixMode = "summary",
        element_id: str | None = None,
    ) -> dict[str, object]:
        if not ctx.is_available():
            return ctx.locked_response()
        outcome = matrix_of_analysis(
            analysis_id,
            store=ctx.store,
            policy=AssuranceExposurePolicy(ctx.max_classification, True),
            read_basis=current_architecture_basis,
            only_elements=(
                None if element_id is None else frozenset({canonical_entity_key(element_id)})
            ),
        )
        match outcome:
            case MatrixAnalysisNotFound():
                return _refusals.not_found(analysis_id, path="analysis_id")
            case MatrixMethodMismatch(actual_method=actual_method):
                return _refusals.not_an_fmea_analysis(analysis_id, actual_method)
            case AnalysisMatrix(rows=rows):
                rendered = list(rows) if mode == "full" else summary_rows(rows)
                return {
                    "analysis_id": analysis_id,
                    "mode": mode,
                    "rows": rendered,
                    "count": len(rendered),
                }
