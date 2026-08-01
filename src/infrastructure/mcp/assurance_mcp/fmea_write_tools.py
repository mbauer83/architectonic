"""The failure-mode factor write tool.

Registered separately from the general assurance write tools because it does not go through the
node/edge mutation protocol: a factor judgement is an append to a revision series, and routing it
through whole-object node editing would destroy exactly the provenance it exists to keep.

VEX assessments, which this follows in every other respect, have no MCP tool — they are a GUI-side
triage flow. This one does, because an FMEA is authored by walking a control structure and rating
what is found, which is agent work.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.assurance.fmea_factors import (
    FactorInvalid,
    FactorNodeNotFound,
    FactorRecorded,
    FactorStoreLocked,
    RecordFactorRequest,
    record_factor_assessment,
)
from src.domain.assurance.fmea_factors import FACTOR_SCALES, FMEA_FACTORS
from src.infrastructure.assurance.write_serialization import run_write
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context


def _scale_help() -> str:
    return "; ".join(f"{factor}: {' < '.join(FACTOR_SCALES[factor])}" for factor in FMEA_FACTORS)


def register_fmea_write_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    @server.tool(
        name="assurance_set_fmea_factor",
        description=(
            "Record a human judgement of one failure-mode factor, as a new immutable revision. "
            "Severity and detectability are normally DERIVED from the model — assert them only to "
            "correct a derivation, with a rationale saying why. Occurrence is asserted-only: "
            "nothing in the model measures a failure rate, so there is no derived value to correct. "
            "Every assertion needs a rationale and an author; a factor sets a priority band, so an "
            "unexplained value cannot be defended in review. "
            f"Scales, weakest to strongest — {_scale_help()}. "
            "`basis_digest` names the picture of the model the judgement was made against (obtain it "
            "from the failure mode's current factor report); when the model moves, the judgement "
            "stops applying and the derived value stands again, with this revision retained. "
            "There is no risk priority number: multiplying ordinals is not a quantity."
        ),
    )
    def assurance_set_fmea_factor(
        node_id: str,
        factor: str,
        value: str,
        justification: str,
        author: str,
        basis_digest: str,
    ) -> dict[str, object]:
        result = run_write(lambda: record_factor_assessment(
            RecordFactorRequest(
                node_id=node_id,
                factor=factor,
                value=value,
                justification=justification,
                author=author,
                basis_digest=basis_digest,
            ),
            store=ctx.store,
            archive=ctx.archive,
        ))
        return _envelope(result, ctx)


def _envelope(result: Any, ctx: Any) -> dict[str, object]:
    if isinstance(result, FactorStoreLocked):
        return ctx.locked_response()
    if isinstance(result, FactorNodeNotFound):
        return {
            "error": "not_a_failure_mode",
            "node_id": result.node_id,
            "message": "no failure mode with this id — a factor rates a failure mode, "
                       "and rating any other node type would record a judgement about nothing",
        }
    if isinstance(result, FactorInvalid):
        return {
            "error": "invalid_factor_assessment",
            "errors": [{"field": e.field, "message": e.message} for e in result.errors],
        }
    assert isinstance(result, FactorRecorded)
    return {
        "node_id": result.node_id,
        "factor": result.factor,
        "value": result.value,
        "revision": result.revision,
        "created_at": result.created_at,
    }
