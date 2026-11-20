"""The failure-mode matrix of one analysis, as every surface asks for it.

A matrix is a projection *of an analysis*. The REST route and the MCP tool both assembled it
themselves, and they disagreed about the part that matters: the route required an FMEA analysis and
refused anything else, while the tool took an optional id and, without one, placed every failure mode
in the store into one grid — the unscoped reading the analysis-aggregate decision removed. Two
assemblies of one projection is how that happened, so there is one here and both call it.

**Rows are scoped; the causal chain behind them is not.** Failure modes are narrowed to the ones the
analysis produced. Everything else is read in full, because a failure mode's hazards belong to the
analysis that produced *them*, and filtering the traversal would report every matrix as incomplete.

**Two renderings of one grid.** The full row is what a recording surface needs: every factor with
its basis and digest, and the drafted occurrence rationale. That draft is one line per fact the
architecture graph holds about the element and is repeated on each of its recorded cells, so for a
well-connected component it dominates the answer by orders of magnitude. The summary row answers
the question the grid exists for — what has been examined, what is left, what is worst — and names
the node to read for the rest.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.application.assurance.exposure import AssuranceExposurePolicy, Visible
from src.application.assurance.fmea_architecture import ArchitectureBasis
from src.application.assurance.fmea_rows import FAILURE_MODE, matrix_rows
from src.application.assurance.ports import ConfidentialAssuranceStore
from src.domain.assurance.fmea_factors import FactorAssessment

FMEA_METHOD = "FMEA"

#: What a summary cell keeps: where it stands and what would advance it. `node_id` is the handle to
#: everything left out — reading that node returns its factors and the digests to record against.
SUMMARY_CELL_FIELDS: tuple[str, ...] = (
    "guideword",
    "state",
    "node_id",
    "action_priority",
    "occurrence_is_requested",
    "next_action",
)


@dataclass(frozen=True)
class AnalysisMatrix:
    """The rows of one FMEA analysis, in the full shape `matrix_rows` produces."""

    analysis_id: str
    rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class MatrixAnalysisNotFound:
    """No such analysis, or one above the session's ceiling — deliberately indistinguishable."""

    analysis_id: str


@dataclass(frozen=True)
class MatrixMethodMismatch:
    """The analysis exists and is readable, and its method defines no failure-mode matrix."""

    analysis_id: str
    actual_method: str


MatrixOutcome = AnalysisMatrix | MatrixAnalysisNotFound | MatrixMethodMismatch


def matrix_of_analysis(
    analysis_id: str,
    *,
    store: ConfidentialAssuranceStore,
    policy: AssuranceExposurePolicy,
    read_basis: Callable[[], ArchitectureBasis],
    only_elements: frozenset[str] | None = None,
) -> MatrixOutcome:
    """Assemble the matrix of `analysis_id`, or say why there is none.

    Exposure-filtered before anything is assembled, so a withheld node cannot influence a count or a
    priority a caller can see. The caller has already established that the store is open.

    `read_basis` is called only once the analysis is known to have a matrix: the architecture graph
    is assembled per request and never cached, and a refusal should not pay for one.
    """
    outcome = policy.apply_analysis(store.get_analysis(analysis_id))
    if not isinstance(outcome, Visible):
        return MatrixAnalysisNotFound(analysis_id)
    method = str(outcome.value.get("method") or "")
    if method != FMEA_METHOD:
        return MatrixMethodMismatch(analysis_id, method)
    visible_nodes, _withheld = policy.filter_nodes(store.list_nodes())
    visible_ids = frozenset(str(node["node_id"]) for node in visible_nodes)
    scoped = [
        node for node in visible_nodes
        if str(node.get("node_type", "")) != FAILURE_MODE
        or str(node.get("analysis_id") or "") == analysis_id
    ]
    failure_mode_ids = [
        str(node["node_id"]) for node in scoped if str(node.get("node_type", "")) == FAILURE_MODE
    ]
    stored = store.read_fmea_assessments(failure_mode_ids)
    rows = matrix_rows(
        nodes=scoped,
        edges=policy.filter_edges(store.list_edges(), visible_ids),
        arch_refs=store.list_arch_refs(),
        assessments={
            node_id: [FactorAssessment.from_row(row) for row in revisions]
            for node_id, revisions in stored.items()
        },
        basis=read_basis(),
        only_elements=only_elements,
    )
    return AnalysisMatrix(analysis_id=analysis_id, rows=tuple(rows))


def summary_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Each row with its cells reduced to `SUMMARY_CELL_FIELDS`; the row's own figures are kept.

    A projection of the full rows rather than a second assembly, so the two renderings cannot
    disagree about a state, a count or a band.
    """
    return [{**row, "cells": [_summary_cell(cell) for cell in _cells_of(row)]} for row in rows]


def _cells_of(row: Mapping[str, object]) -> Sequence[Mapping[str, object]]:
    cells = row["cells"]
    assert isinstance(cells, Sequence)
    return cells


def _summary_cell(cell: Mapping[str, object]) -> dict[str, object]:
    return {name: cell[name] for name in SUMMARY_CELL_FIELDS}
