"""Activity per-diagram verification contributions (W045, W047).

Wrapped as a `DiagramVerificationContribution` so the central verifier imports no activity symbol:
what counts as a drawn step is the activity module's question, and only this module knows that a
fork carries nothing to read.
"""

from __future__ import annotations

from typing import Any

from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext

from ._step_links import LABELLED_STEP_KINDS, drawn_step_ids, sentinel_target


class _StepCoverageContribution:
    """W045 — a step the model declares that the stored body does not draw.

    The high-severity half of the defect this exists for was that it was invisible: a diagram
    missing a quarter of its steps verified clean, because every rule looked at the model and none
    at the picture. So this reads the **stored** body. Re-rendering from `diagram-entities` and
    comparing would put the renderer against itself and pass by construction, which is exactly the
    staleness it needs to catch.

    A warning, not an error: every repository holding an affected body starts reporting this on
    upgrade, on content authored in good faith, and the remedy is one re-render.

    What it does not catch: a step drawn in the wrong *place* — inside one arm of a decision that
    both arms reach, say. Presence is readable off a line; placement needs the body's nesting, and
    that reading lives only in the renderer's own gate. So this sees an omitted step and not a
    misplaced one.
    """

    diagnostic_codes: tuple[str, ...] = ("W045",)

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        del candidate
        if not ctx.body:
            return
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415

        drawn = drawn_step_ids(ctx.body)
        for kind, step in _declared_steps(ctx.fm):
            step_id = str(step.get("id") or "")
            if not step_id or sentinel_target(step) in drawn:
                continue
            result.issues.append(Issue(
                Severity.WARNING,
                "W045",
                f"{kind.capitalize()} '{step_id}' is declared in diagram-entities but the stored "
                f"body does not draw it. Re-render with puml=\"auto-sync\".",
                ctx.loc,
            ))


def _declared_steps(fm: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The declared steps whose emission carries a sentinel, so absence from the body is readable."""
    entities = fm.get("diagram-entities")
    if not isinstance(entities, dict):
        return []
    declared: list[tuple[str, dict[str, Any]]] = []
    for kind in LABELLED_STEP_KINDS:
        items = entities.get(kind)
        if isinstance(items, list):
            declared.extend((kind, item) for item in items if isinstance(item, dict))
    return declared


#: The three edges a decision declares: the true branch, the false branch, and the step the two
#: converge on once the decision closes.
_THEN, _ELSE, _FLOW = "step-then", "step-else", "step-flow"


def _decision_edges(fm: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Per decision id, its outgoing branch and merge targets keyed by connection type."""
    connections = fm.get("connections")
    if not isinstance(connections, list):
        return {}
    edges: dict[str, dict[str, str]] = {}
    for item in connections:
        if not isinstance(item, dict):
            continue
        conn_type = str(item.get("conn_type") or "")
        if conn_type not in (_THEN, _ELSE, _FLOW):
            continue
        source, target = str(item.get("source") or ""), str(item.get("target") or "")
        if source and target:
            edges.setdefault(source, {})[conn_type] = target
    return edges


class _MergeTargetContribution:
    """W047 — a decision whose merge edge names a step one of its own branches already names.

    A decision declares three edges: `step-then`, `step-else`, and a `step-flow` naming the step the
    branches converge on once it closes. Pointing that merge edge at a step a branch already names
    says two contradictory things — the step is both the content of one branch and what follows the
    whole decision — and its only observable effect is that the renderer emits that step, and its
    entire downstream chain, twice: once inside the branch and once after the `endif`. Nested
    decisions compound it multiplicatively.

    Measured on a five-decision diagram carrying four such declarations: the release tail was drawn
    four times and one step seven times, at 3205 x 3544 px. With the four edges withheld, once and
    three times, at 2910 x 1705. `artifact_verify` reported 0 errors and 0 warnings throughout, and
    the diagram was valid — nothing was lost, the picture simply described a workflow that did not
    exist, and a reader was the only thing that could notice.

    One comparison per decision, no traversal. It names the declaration rather than the drawing,
    because the declaration is what someone can fix; a first diagnosis blamed the graph's cycles and
    was wrong — withholding the cyclic edge changed no count.

    A warning: an existing repository holding these verifies clean today, the diagram still renders,
    and the remedy is an authoring decision — either the merge edge is redundant and goes, or the
    branch is wrong.
    """

    diagnostic_codes: tuple[str, ...] = ("W047",)

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        del candidate
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415

        for decision_id, edges in sorted(_decision_edges(ctx.fm).items()):
            merge = edges.get(_FLOW)
            if not merge:
                continue
            for branch in (_THEN, _ELSE):
                if edges.get(branch) != merge:
                    continue
                result.issues.append(Issue(
                    Severity.WARNING,
                    "W047",
                    f"Decision '{decision_id}' declares {_FLOW} to '{merge}', which its {branch} "
                    f"already names. The step and everything after it is drawn twice — once in the "
                    f"branch and once after the decision closes. Remove the {_FLOW} edge if the "
                    f"branch is right, or retarget it at the step the branches truly converge on.",
                    ctx.loc,
                ))


STEP_COVERAGE_CONTRIBUTION = _StepCoverageContribution()
MERGE_TARGET_CONTRIBUTION = _MergeTargetContribution()
