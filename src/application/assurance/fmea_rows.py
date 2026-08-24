"""Assembling the failure-mode matrix: which elements are offered rows, and why.

**The candidate set is a nomination, never a census.** Enumerating failure modes for every
architecture element is the classic death march — this repository holds hundreds of entities, and
against five guidewords that is thousands of cells nobody finishes. The elements a control
structure already names are a handful, which is a session a person can complete. Scoping this way
also strengthens the attachment to the hazard analysis rather than weakening it: you analyse the
components that analysis already says matter.

**One nominator: the analysis.** Elements bound by a control-structure node get rows.

The architecture graph also knows which elements are load-bearing, and a component nobody has drawn
into a control structure is invisible to the analysis. That signal is real and it is *not* dropped —
but it is reported as a coverage finding, not as rows. Measured on the repository this software
describes, nominating structurally load-bearing elements produced 107 rows beside the 3 the analysis
had reached, which is the death march above rather than an addition to a session. Tightening the
thresholds did not rescue it: the same model yields 72, 31 or 23 depending on numbers that have no
principled defence, and most "sole providers" turn out to be ordinary two-element links where one
dependent happens to have exactly one provider.

So the graph's claim reaches the analyst as a statement they can act on — *this element is
load-bearing, nothing has analysed it, here is what relies on it* — and acting on it means adding the
element deliberately, which is a caller's act rather than something this module offers in bulk.

Vulnerability findings are deliberately *not* a nominator either. They are one narrow slice of hazard
and risk, irrelevant to most safety and operational analyses, and a candidate list led by them would
mis-frame the method.

What a cell then reports lives next door, in `assurance_fmea_cells`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.application.assurance.fmea_architecture import ArchitectureBasis
from src.application.assurance.fmea_cells import cell_for, cell_payload
from src.application.assurance.fmea_occurrence_evidence import ElementSecurityBasis
from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.assurance_node_types import CONTROL_STRUCTURE_NODE
from src.domain.assurance.failure_modes import (
    ANSWERED_ASSESSMENT_STATES,
    FAILURE_GUIDEWORDS,
)
from src.domain.assurance.fmea_action_priority import worst_band
from src.domain.assurance.fmea_factors import (
    FactorAssessment,
)

FAILURE_MODE = "failure-mode"
BINDS_TO = "binds-to"


@dataclass(frozen=True)
class Candidate:
    """One architecture element the matrix offers rows for, and why it is offered."""

    element_id: str
    nominated_by: tuple[str, ...]
    """Why this row exists. Kept as a list though only `control-structure` occurs today, because a
    reader needs to know on what grounds an element is being asked about, and a future nominator
    would otherwise be indistinguishable from this one."""


def candidates(
    *,
    nodes: Sequence[Mapping[str, object]],
    arch_refs: Sequence[Mapping[str, object]],
) -> tuple[Candidate, ...]:
    """The elements the analysis has named, which are the elements it offers rows for."""
    node_types = {str(n["node_id"]): str(n.get("node_type", "")) for n in nodes}
    # Keyed on the stable form to meet the graph nominations below, which `typed_edges` already
    # canonicalises. The two nominations come from different stores that do not agree on whether
    # an id carries its slug; unnormalised, the set difference fails to subtract and the same
    # element is nominated twice, under two names.
    from_analysis = {
        canonical_entity_key(str(ref["arch_artifact_id"]))
        for ref in arch_refs
        if str(ref.get("ref_type")) == BINDS_TO
        and node_types.get(str(ref["assurance_node_id"])) == CONTROL_STRUCTURE_NODE
    }
    return tuple(
        Candidate(element_id=element, nominated_by=("control-structure",))
        for element in sorted(from_analysis)
    )


def element_label(element_id: str, basis: ArchitectureBasis) -> str:
    """The element's reader-facing name, or "" when the architecture model cannot describe it.

    `display_label` first: it is what the rest of the product shows for an element, so a matrix that
    fell back to the raw `name` would label the same element differently from every other surface.
    """
    entity = basis.entities.get(element_id, {})
    return str(entity.get("display_label") or entity.get("name") or "")


def element_type(element_id: str, basis: ArchitectureBasis) -> str:
    """The element's artifact type, or "" when the architecture model cannot describe it."""
    return str(basis.entities.get(element_id, {}).get("artifact_type") or "")


def matrix_rows(
    *,
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
    arch_refs: Sequence[Mapping[str, object]],
    assessments: Mapping[str, Sequence[FactorAssessment]],
    basis: ArchitectureBasis = ArchitectureBasis(),
    security: Mapping[str, ElementSecurityBasis] | None = None,
    only_elements: frozenset[str] | None = None,
) -> list[dict[str, object]]:
    """One row per candidate element, each with a cell per guideword.

    `only_elements` narrows the work to the elements a caller actually needs. An entity page wants
    one row, and deriving every other element's factors to find it would make one page load pay for
    the whole matrix.
    """
    by_element: dict[str, dict[str, Mapping[str, object]]] = {}
    node_by_id = {str(n["node_id"]): n for n in nodes}
    for ref in arch_refs:
        if str(ref.get("ref_type")) != BINDS_TO:
            continue
        node = node_by_id.get(str(ref["assurance_node_id"]))
        if node is None or str(node.get("node_type", "")) != FAILURE_MODE:
            continue
        guideword = str(node.get("failure_type") or "")
        element_key = canonical_entity_key(str(ref["arch_artifact_id"]))
        by_element.setdefault(element_key, {})[guideword] = node

    rows: list[dict[str, object]] = []
    for candidate in candidates(nodes=nodes, arch_refs=arch_refs):
        if only_elements is not None and candidate.element_id not in only_elements:
            continue
        placed = by_element.get(candidate.element_id, {})
        cells = [
            cell_for(
                candidate.element_id, guideword.slug, placed.get(guideword.slug),
                nodes=nodes, edges=edges, assessments=assessments, basis=basis,
                security=(security or {}).get(candidate.element_id, ElementSecurityBasis()),
            )
            for guideword in FAILURE_GUIDEWORDS
        ]
        answered = sum(1 for cell in cells if cell.state in ANSWERED_ASSESSMENT_STATES)
        rows.append({
            "element_id": candidate.element_id,
            # How to name the row. An id alone tells an analyst nothing about which element they are
            # being asked to assess, and 107 of them read as noise; both come from the basis, which
            # is the one place these surfaces obtain the architecture graph. Empty when the model is
            # unavailable — the row still exists, keyed by the id, which is honest rather than
            # inventing a label for an element nothing can describe.
            "element_name": element_label(candidate.element_id, basis),
            "element_type": element_type(candidate.element_id, basis),
            "nominated_by": list(candidate.nominated_by),
            "cells": [cell_payload(cell) for cell in cells],
            "answered_cells": answered,
            "unanswered_cells": len(cells) - answered,
            "worst_action_priority": worst_band([c.action_priority for c in cells if c.node_id]),
        })
    return rows


