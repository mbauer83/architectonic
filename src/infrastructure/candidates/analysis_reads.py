"""A stress analysis read against its naive candidate, shared by the HTTP and MCP transports.

The analysis document's typed tables and the candidate it names, and what is derived from the two:
progress, coverage, incidence and coupling. Coverage counts the perspectives this repository offers
(`repository_perspectives`). Candidates themselves are `CandidateService`'s; this only reads them.
"""
from __future__ import annotations

from typing import Any

from src.application.artifacts.document_table_rows import DocumentTables, tables_of_stored_document
from src.application.change_sets.candidate_reads import read_view
from src.application.stress_analysis.workspace import analyse
from src.domain.repository.repo_default_stress_analysis import NAIVE_CANDIDATE, STRESS_ANALYSIS
from src.infrastructure.candidates.perspectives import repository_perspectives
from src.infrastructure.candidates.repository import NotStored
from src.infrastructure.candidates.service import CandidateService


def analysis_tables(service: CandidateService, ref: str) -> tuple[str, str, DocumentTables]:
    """The analysis document's id, its naive candidate's id and its typed tables; not found for any other document."""
    doc = service.index.get_document(ref)
    if doc is None or doc.doc_type != STRESS_ANALYSIS:
        raise NotStored(f"No stress analysis {ref} is stored.")
    naive = str(doc.extra.get(NAIVE_CANDIDATE) or "")
    if not naive:
        raise ValueError("Set naive-candidate on the stress-analysis document.")
    stored = service.store.find(naive)
    tables = tables_of_stored_document(doc.path, doc.doc_type, [service.root])
    return doc.artifact_id, stored.id if stored else naive, tables


def analysis(service: CandidateService, ref: str) -> dict[str, Any]:
    document, naive, tables = analysis_tables(service, ref)
    view = read_view(service.store.require(naive), service.store, service.registry)
    return {
        "document": document, "naive_candidate": naive,
        **analyse(tables, view, repository_perspectives(service.root)),
    }


def progress(service: CandidateService, ref: str) -> dict[str, Any]:
    report = analysis(service, ref)
    return {key: report[key] for key in ("document", "naive_candidate", "progress", "coverage")}


def incidence(service: CandidateService, ref: str) -> dict[str, Any]:
    report = analysis(service, ref)
    return {key: value for key, value in report.items() if key not in {"progress", "coverage"}}
