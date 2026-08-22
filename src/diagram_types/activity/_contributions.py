"""Activity per-diagram verification contributions (W045).

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


STEP_COVERAGE_CONTRIBUTION = _StepCoverageContribution()
