"""Candidate and stress-analysis operations over the engagement repository.

One tool per operation, as the REST surface has one route per operation (ADR "MCP Surface Topology": no
mode-multiplexed tools). The arguments are the REST bodies' own models (`candidate_wire`), so the two
surfaces cannot come to accept different edits; the descriptions are `candidate_tool_descriptions`.
"""

from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]
from pydantic import Field

from src.application.artifacts.document_part_edits import TableRowEdits
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.candidate_wire import CandidateHeader, CandidatePatch, RecordedEdit
from src.infrastructure.candidates import evaluation
from src.infrastructure.candidates.service import CandidateService, document_writer
from src.infrastructure.mcp.artifact_mcp import candidate_tool_descriptions as said
from src.infrastructure.mcp.artifact_mcp.context import (
    authoritative_callbacks_for,
    registry_cached,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, LOCAL_WRITE, READ_ONLY
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.document import edit_document
from src.infrastructure.write.artifact_write.types import WriteResult

CandidateId = Annotated[str, Field(description="A candidate architecture's id, in either spelling.")]
AnalysisId = Annotated[str, Field(description="A stress-analysis document's id, in either spelling.")]
BasedOn = Annotated[str, Field(description="The `version` the last read or write of the candidate answered.")]
RepoRoot = Annotated[str | None, Field(description="The engagement repository; the active one when omitted.")]


def _roots(repo_root: str | None) -> list[Path]:
    return resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)


def _service(repo_root: str | None) -> CandidateService:
    return CandidateService(_roots(repo_root)[0])


def _dumped(edits: list[RecordedEdit]) -> list[dict[str, Any]]:
    return [edit.model_dump(exclude_unset=True) for edit in edits]


def change_set_list(repo_root: RepoRoot = None) -> dict[str, Any]:
    return {"candidates": _service(repo_root).list()}


def change_set_read(artifact_id: CandidateId, repo_root: RepoRoot = None) -> dict[str, Any]:
    return _service(repo_root).read(artifact_id)


def change_set_standing(artifact_id: CandidateId, repo_root: RepoRoot = None) -> dict[str, Any]:
    return _service(repo_root).standing(artifact_id)


def change_set_compare(
    artifact_id: CandidateId,
    base: Annotated[str, Field(description="`model`, `naive`, or another candidate's id.")] = "model",
    naive: Annotated[str | None, Field(description="The naive candidate's id, with base `naive`.")] = None,
    diagram: Annotated[
        str | None, Field(description="A stored diagram to draw on, instead of the one the candidate is drawn on."),
    ] = None,
    repo_root: RepoRoot = None,
) -> dict[str, Any]:
    return _service(repo_root).compare(artifact_id, base, naive, diagram, process_runtime_catalogs().ontology)


def change_set_residuality(artifact_id: CandidateId, repo_root: RepoRoot = None) -> dict[str, Any]:
    return evaluation.residuality_by_analysis(_service(repo_root), artifact_id)


def change_set_check(
    candidates: Annotated[list[str], Field(min_length=1, description="Distinct candidate ids, drafts or offered.")],
    repo_root: RepoRoot = None,
) -> dict[str, Any]:
    return _service(repo_root).check(candidates)


def change_set_create(
    record: CandidateHeader,
    operations: Annotated[list[RecordedEdit] | None, Field(description="Edits recorded in the same write.")] = None,
    repo_root: RepoRoot = None,
) -> dict[str, Any]:
    return _service(repo_root).create(record.model_dump(exclude_unset=True), _dumped(operations or []))


def change_set_record(
    artifact_id: CandidateId,
    based_on: BasedOn,
    operations: Annotated[list[RecordedEdit], Field(min_length=1, description="Edits, recorded in order.")],
    repo_root: RepoRoot = None,
) -> dict[str, Any]:
    return _service(repo_root).record(artifact_id, based_on, _dumped(operations))


def change_set_edit(
    artifact_id: CandidateId, based_on: BasedOn, patch: CandidatePatch, repo_root: RepoRoot = None,
) -> dict[str, Any]:
    return _service(repo_root).edit(artifact_id, based_on, patch.stated())


def change_set_delete(
    artifact_id: CandidateId,
    based_on: Annotated[str | None, Field(description="The version last read; refuses a changed candidate.")] = None,
    dry_run: bool = True,
    repo_root: RepoRoot = None,
) -> dict[str, Any]:
    return _service(repo_root).delete(artifact_id, based_on=based_on, dry_run=dry_run)


def change_set_rebase(artifact_id: CandidateId, based_on: BasedOn, repo_root: RepoRoot = None) -> dict[str, Any]:
    return _service(repo_root).rebase(artifact_id, based_on)


def change_set_apply(artifact_id: CandidateId, dry_run: bool = True, repo_root: RepoRoot = None) -> dict[str, Any]:
    return _service(repo_root).apply(artifact_id, dry_run=dry_run)


def analysis_start(
    title: Annotated[str, Field(min_length=1, description="The analysis document's title.")],
    naive: CandidateHeader,
    context: Annotated[
        str | None, Field(description="The environment, and the decision the evaluation informs; free text."),
    ] = None,
    repo_root: RepoRoot = None,
) -> dict[str, Any]:
    roots = _roots(repo_root)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    writer = document_writer(roots[0], verifier_for(roots_key(roots), include_registry=False), clear_repo_caches)
    try:
        return CandidateService(roots[0]).start(
            title, naive.model_dump(exclude_unset=True), writer, context=context,
        )
    finally:
        mutation_context.finalize()


def analysis_progress(artifact_id: AnalysisId, repo_root: RepoRoot = None) -> dict[str, Any]:
    return _service(repo_root).progress(artifact_id)


def analysis_incidence(artifact_id: AnalysisId, repo_root: RepoRoot = None) -> dict[str, Any]:
    return _service(repo_root).incidence(artifact_id)


def analysis_test_set(artifact_id: AnalysisId, repo_root: RepoRoot = None) -> dict[str, Any]:
    return evaluation.evaluation(_service(repo_root), artifact_id)


def analysis_perspectives() -> dict[str, Any]:
    return evaluation.perspectives()


def analysis_hold_out_test_set(
    artifact_id: AnalysisId,
    seed: Annotated[int | None, Field(description="The draw's seed; the analysis's own when omitted.")] = None,
    dry_run: bool = True,
    repo_root: RepoRoot = None,
) -> dict[str, Any]:
    roots = _roots(repo_root)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)

    def write(document: str, edits: TableRowEdits, dry: bool) -> WriteResult:
        return edit_document(
            assert_write_root=assert_engagement_write_root, repo_root=roots[0],
            verifier=verifier_for(roots_key(roots), include_registry=False), clear_repo_caches=clear_repo_caches,
            artifact_id=document, registry=registry_cached(roots_key(roots)), repo=repo_cached(roots_key(roots)),
            part=edits, title=None, body=None, keywords=None, extra_frontmatter=None, status=None, version=None,
            last_updated=None, dry_run=dry,
        )

    held = evaluation.hold_out(CandidateService(roots[0]), artifact_id, write, seed=seed, dry_run=dry_run)
    if held["wrote"] and not dry_run:
        mutation_context.finalize()
    return held


_READ_TOOLS = (
    (change_set_list, said.CHANGE_SET_LIST),
    (change_set_read, said.CHANGE_SET_READ),
    (change_set_standing, said.CHANGE_SET_STANDING),
    (change_set_compare, said.CHANGE_SET_COMPARE),
    (change_set_residuality, said.CHANGE_SET_RESIDUALITY),
    (change_set_check, said.CHANGE_SET_CHECK),
    (analysis_progress, said.ANALYSIS_PROGRESS),
    (analysis_incidence, said.ANALYSIS_INCIDENCE),
    (analysis_test_set, said.ANALYSIS_TEST_SET),
    (analysis_perspectives, said.ANALYSIS_PERSPECTIVES),
)

#: Each write tool, what it says, and whether it only adds (a create) or may replace or remove.
_WRITE_TOOLS = (
    (change_set_create, said.CHANGE_SET_CREATE, LOCAL_WRITE),
    (change_set_record, said.CHANGE_SET_RECORD, DESTRUCTIVE_LOCAL_WRITE),
    (change_set_edit, said.CHANGE_SET_EDIT, DESTRUCTIVE_LOCAL_WRITE),
    (change_set_rebase, said.CHANGE_SET_REBASE, DESTRUCTIVE_LOCAL_WRITE),
    (change_set_apply, said.CHANGE_SET_APPLY, DESTRUCTIVE_LOCAL_WRITE),
    (change_set_delete, said.CHANGE_SET_DELETE, DESTRUCTIVE_LOCAL_WRITE),
    (analysis_start, said.ANALYSIS_START, LOCAL_WRITE),
    (analysis_hold_out_test_set, said.ANALYSIS_HOLD_OUT, DESTRUCTIVE_LOCAL_WRITE),
)


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def register_candidate_read_tools(mcp: MCPServer) -> None:
    for tool, description in _READ_TOOLS:
        mcp.tool(
            name=tool.__name__, title=_title(tool.__name__), description=description, annotations=READ_ONLY,
            structured_output=True,
        )(tool)


def register_candidate_write_tools(mcp: MCPServer) -> None:
    for tool, description, annotations in _WRITE_TOOLS:
        register_mutation_tool(
            mcp, tool, name=tool.__name__, title=_title(tool.__name__), description=description,
            annotations=annotations,
        )
