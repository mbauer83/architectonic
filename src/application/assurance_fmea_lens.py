"""The failure-mode roll-up an architecture entity page shows.

A component page has to answer "is there anything here for me" in one glance, without anyone
navigating to the assurance area to find out. That is three facts: the worst priority band among
this element's failure modes, how many rows are at it, and how many cells nobody has examined.

Returns nothing at all when the element is not a candidate, so a page shows no widget rather than
an empty one — an empty panel reads as "analysed, nothing found", which is the opposite of what an
absent candidate means.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_fmea_architecture import ArchitectureBasis
from src.application.assurance_fmea_rows import matrix_rows
from src.application.assurance_ports import ConfidentialAssuranceStore
from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.fmea_action_priority import HIGH
from src.domain.assurance.fmea_factors import FactorAssessment

FAILURE_MODE = "failure-mode"


@dataclass(frozen=True)
class FailureModeRollUp:
    worst_action_priority: str | None
    high_count: int
    unanswered_cells: int
    nominated_by: tuple[str, ...]


def _as_assessment(row: Mapping[str, object]) -> FactorAssessment:
    return FactorAssessment(
        node_id=str(row.get("node_id") or ""),
        factor=str(row.get("factor") or ""),
        basis_digest=str(row.get("basis_digest") or ""),
        revision=int(str(row.get("revision") or 0)),
        value=str(row.get("value") or ""),
        justification=str(row.get("justification") or ""),
        author=str(row.get("author") or ""),
        created_at=str(row.get("created_at") or ""),
    )


def _row_for(
    arch_artifact_id: str,
    *,
    store: ConfidentialAssuranceStore,
    policy: AssuranceExposurePolicy,
    nodes: Sequence[Mapping[str, object]],
    basis: ArchitectureBasis = ArchitectureBasis(),
) -> dict[str, object] | None:
    """The matrix row for one element, or None when it is not a candidate.

    Shared by both projections below so the derivation runs one way. The scoping matters: a page
    asking about one component must not pay to derive every element's factors, nor to read every
    judgement in the store.
    """
    arch_refs = list(store.list_arch_refs())
    # The GUI navigates by the full slugged id; the store keys on the stable one. Compared raw,
    # an element's own entity page reports no failure modes while the matrix shows several.
    element_key = canonical_entity_key(arch_artifact_id)
    bound_here = {
        str(ref["assurance_node_id"]) for ref in arch_refs
        if canonical_entity_key(str(ref.get("arch_artifact_id") or "")) == element_key
    }
    visible_ids = frozenset(str(n["node_id"]) for n in nodes)
    edges = policy.filter_edges(list(store.list_edges()), visible_ids)
    failure_mode_ids = [
        str(n["node_id"]) for n in nodes
        if str(n.get("node_type", "")) == FAILURE_MODE and str(n["node_id"]) in bound_here
    ]
    stored = store.read_fmea_assessments(failure_mode_ids)
    rows = matrix_rows(
        nodes=list(nodes),
        edges=edges,
        arch_refs=arch_refs,
        assessments={
            node_id: [_as_assessment(row) for row in revisions]
            for node_id, revisions in stored.items()
        },
        basis=basis,
        only_elements=frozenset({element_key}),
    )
    return next((r for r in rows if r["element_id"] == element_key), None)


def failure_mode_summary(
    arch_artifact_id: str,
    *,
    store: ConfidentialAssuranceStore,
    policy: AssuranceExposurePolicy,
    nodes: Sequence[Mapping[str, object]],
    basis: ArchitectureBasis = ArchitectureBasis(),
) -> dict[str, object] | None:
    """This element's row, rolled up, or None when it is not a candidate."""
    row = _row_for(arch_artifact_id, store=store, policy=policy, nodes=nodes, basis=basis)
    if row is None:
        return None
    cells = row["cells"]
    assert isinstance(cells, list)
    rolled = FailureModeRollUp(
        worst_action_priority=row["worst_action_priority"],  # type: ignore[arg-type]
        high_count=sum(1 for c in cells if c["action_priority"] == HIGH),
        unanswered_cells=int(str(row["unanswered_cells"])),
        nominated_by=tuple(row["nominated_by"]),  # type: ignore[arg-type]
    )
    return {
        "worst_action_priority": rolled.worst_action_priority,
        "high_count": rolled.high_count,
        "unanswered_cells": rolled.unanswered_cells,
        "nominated_by": list(rolled.nominated_by),
    }


def factor_report(
    failure_mode_id: str,
    *,
    store: ConfidentialAssuranceStore,
    policy: AssuranceExposurePolicy,
    nodes: Sequence[Mapping[str, object]],
    basis: ArchitectureBasis = ArchitectureBasis(),
) -> dict[str, object] | None:
    """One failure mode's factors, each with the basis digest a judgement must be recorded against.

    Exists because recording a factor is impossible without it. A judgement applies only while the
    digest of the model inputs it was made against still matches, and the digest is computed, not
    chosen — so a caller has to be able to read it. Occurrence is the case that makes this a blocker
    rather than an inconvenience: it is asserted-only, with no derived value to fall back on, so a
    judgement filed against a digest that never matched leaves the row undecidable for good.

    Built by scoping the matrix to this failure mode's own element and picking its cell, so there is
    one derivation path rather than a second implementation of the same arithmetic.
    """
    element = next(
        (
            canonical_entity_key(str(ref["arch_artifact_id"]))
            for ref in store.list_arch_refs(assurance_node_id=failure_mode_id)
            if str(ref.get("ref_type")) == "binds-to"
        ),
        None,
    )
    if element is None:
        return None
    summary_row = _row_for(element, store=store, policy=policy, nodes=nodes, basis=basis)
    if summary_row is None:
        return None
    cells = summary_row["cells"]
    assert isinstance(cells, list)
    cell = next((c for c in cells if c.get("node_id") == failure_mode_id), None)
    if cell is None:
        return None
    return {
        "failure_mode_id": failure_mode_id,
        "element_id": element,
        "guideword": cell["guideword"],
        "action_priority": cell["action_priority"],
        "occurrence_is_requested": cell["occurrence_is_requested"],
        "next_action": cell["next_action"],
        "factors": cell["factors"],
    }
