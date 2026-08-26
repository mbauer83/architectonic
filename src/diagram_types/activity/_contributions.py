"""Activity per-diagram verification contributions (W045, W047, W048).

Wrapped as a `DiagramVerificationContribution` so the central verifier imports no activity symbol:
what counts as a drawn step is the activity module's question, and only this module knows that a
fork carries nothing to read.
"""

from __future__ import annotations

from typing import Any

from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext

from ._edge_collisions import colliding_declarations
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


class _EdgeCollisionContribution:
    """W048 — declared step edges the renderer's index can hold only one of.

    W045 asks whether every declared *step* is drawn. Nothing asked it of a declared *edge*, and the
    loss starts earlier than any walk: `_build_single_target` is a dict comprehension keyed by
    `source`, so a second `step-flow`, `step-then`, `step-else`, `step-contains` or `step-in-lane` out
    of one step is discarded when the index is built. `_build_notes_index` is keyed by **target**, so
    two notes on one step lose one — the same accident with the opposite key. `_build_multi_target`
    sits beside them and does not lose; it is used for exactly one type, `step-fork-branch`.

    Verified rather than assumed: two `step-flow` out of one step index to the second alone, and two
    notes on one step to the second alone.

    **A declaration-side answer, not a walk-side one.** The decision is `colliding_declarations`, a
    grouping over declared data with no traversal — which is what makes it complete: an edge of a
    single-target type is either alone under its key or not, and there is no third case. Two earlier
    designs asked the walk or the emission and neither could be complete or observable.

    It names the survivor as well as the losses, because an author cannot tell from "several edges
    collided" whether the one the picture kept is the one they meant — and the survivor is the *last*
    declared, which is not a rule anybody would guess.

    A warning: a repository holding these verifies clean today and the diagram still renders. The
    remedy is an authoring decision, and for a partition it is written down — the ontology's own
    guidance says to connect the first contained step with `step-contains` and chain the rest with
    `step-flow`, while its declared cardinality permits many. This reports the picture's behaviour
    rather than adjudicating that.
    """

    diagnostic_codes: tuple[str, ...] = ("W048",)

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        del candidate
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415

        connections = ctx.fm.get("connections")
        if not isinstance(connections, list):
            return
        declared = [item for item in connections if isinstance(item, dict)]
        for collision in colliding_declarations(declared):
            lost = ", ".join(f"{source} → {target}" for source, target in collision.lost)
            kept_source, kept_target = collision.kept
            result.issues.append(Issue(
                Severity.WARNING,
                "W048",
                f"'{collision.keyed_on}' declares {len(collision.edges)} {collision.conn_type} edges, "
                f"and the drawing can carry one. It draws {kept_source} → {kept_target}; "
                f"{lost} is not drawn anywhere. Keep one edge of this type here and express the rest "
                f"another way.",
                ctx.loc,
            ))


STEP_COVERAGE_CONTRIBUTION = _StepCoverageContribution()
MERGE_TARGET_CONTRIBUTION = _MergeTargetContribution()
EDGE_COLLISION_CONTRIBUTION = _EdgeCollisionContribution()
