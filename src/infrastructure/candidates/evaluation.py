"""The test set of a stress analysis, shared by the HTTP and MCP transports.

Reads: the test set and every judged architecture's standing; the residuality a candidate earned in
each analysis that judged it; the perspectives offered to whoever writes stressors. One write: a
random third of the design stressors held out into the test set, the seed answered so it can be drawn
again. Test stressors and verdicts are otherwise ordinary rows of the analysis document, written as
every row is.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from src.application.artifacts.document_part_edits import RowChange, TableRowEdits
from src.application.artifacts.document_table_edits import row_values
from src.application.change_sets.stacking import descendants
from src.application.stress_analysis.evaluation import evaluate, held_out, seed_for
from src.application.stress_analysis.rows import held_apart, in_test_set, rows_of
from src.domain.repository.repo_default_stress_analysis import NAIVE_CANDIDATE, STRESS_ANALYSIS, TEST_SET
from src.domain.repository.repo_default_stress_perspectives import STRESS_PERSPECTIVES
from src.infrastructure.candidates.repository import CandidateConflict
from src.infrastructure.candidates.service import CandidateService
from src.infrastructure.write.artifact_write.types import WriteResult

#: A document's table rows written, bound by the transport to its verifier: document id, the edits, dry run.
TableWriter: TypeAlias = Callable[[str, TableRowEdits, bool], WriteResult]


def evaluation(service: CandidateService, ref: str) -> dict[str, Any]:
    """The analysis's test set, its verdicts, the standing of every judged or integrated architecture, and the stage."""
    document, naive, tables = service.analysis_tables(ref)
    candidates = service.store.list()
    stacked = descendants(naive, candidates)
    integrated = [one.id for one in candidates if one.id in stacked and one.state == "integrated"]
    design = [row for row in rows_of(tables, "stressors") if not in_test_set(row)]
    return {
        "document": document, "naive_candidate": naive, "design_stressors": len(design),
        **evaluate(tables, integrated=integrated, adapted=bool(stacked), known=[one.id for one in candidates]),
    }


def hold_out(
    service: CandidateService, ref: str, write: TableWriter, *, seed: int | None, dry_run: bool,
) -> dict[str, Any]:
    """Move a random third of the design stressors into the test set, in one row edit of the stressors table."""
    document, _naive, tables = service.analysis_tables(ref)
    stressors, held = tables.table("stressors"), held_apart(tables)
    every = list(stressors.rows) if stressors else []
    rows = [row for row in every if row.row_id not in held]
    # Drawn over every stressor the analysis holds, in the document's order: before a hold-out that is
    # the design set, and after one it is the same set, so a retry draws again what it drew the first time.
    drawn_from = [row.row_id for row in every]
    drawn_with = seed_for(document, drawn_from) if seed is None else seed
    if held:
        return _held_already(document, drawn_from, held, drawn_with, dry_run)
    chosen = set(held_out(drawn_from, drawn_with))
    edits = TableRowEdits("stressors", tuple(
        RowChange(row.row_id, row_values(row), {"set": TEST_SET}) for row in rows if row.row_id in chosen
    ))
    written = write(document, edits, dry_run)
    if written.error_messages or (not dry_run and not written.wrote):
        raise ValueError(f"The hold-out cannot be written: {' '.join(written.error_messages) or 'it was refused'}")
    return {
        "document": document, "seed": drawn_with, "dry_run": dry_run, "wrote": bool(written.wrote),
        "design_stressors": len(rows), "held_out": [row.row_id for row in rows if row.row_id in chosen],
    }


def _held_already(
    document: str, drawn_from: list[str], held: frozenset[str], seed: int, dry_run: bool,
) -> dict[str, Any]:
    """A hold-out asked of an analysis that already has a test set: the same draw again is answered as
    done, writing nothing; anything else is refused, since a second third would shrink the design set."""
    if set(held_out(drawn_from, seed)) == held:
        return {
            "document": document, "seed": seed, "dry_run": dry_run, "wrote": False,
            "design_stressors": len(drawn_from), "held_out": [ref for ref in drawn_from if ref in held],
        }
    raise CandidateConflict(
        f"{document} already holds a test set ({', '.join(ref for ref in drawn_from if ref in held)}), and this "
        "hold-out would draw another. Add test stressors as rows of the stressors table with set = test, "
        "or move a stressor back to the design set first."
    )


def residuality_by_analysis(service: CandidateService, candidate: str) -> dict[str, Any]:
    """The candidate's standing in every analysis that judged it, or integrated it, against its test set."""
    candidate = service.resolved(candidate)
    standings = []
    for doc in service.index.list_documents(doc_type=STRESS_ANALYSIS):
        if not doc.extra.get(NAIVE_CANDIDATE):
            continue
        read = evaluation(service, doc.artifact_id)
        standing = next((one for one in read["architectures"] if one["architecture"] == candidate), None)
        if standing is not None:
            standings.append({"document": doc.artifact_id, "title": doc.title, **standing})
    return {"candidate": candidate, "analyses": standings}


def perspectives() -> dict[str, Any]:
    """The frameworks offered to whoever writes stressors, each perspective with its guiding question."""
    return {"frameworks": [
        {"id": framework.id, "name": framework.name, "perspectives": [
            {"id": one.id, "name": one.name, "kind": one.kind, "question": one.question}
            for one in framework.perspectives
        ]}
        for framework in STRESS_PERSPECTIVES
    ]}
