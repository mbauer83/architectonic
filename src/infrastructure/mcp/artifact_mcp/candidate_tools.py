"""Candidate and stress-analysis operations over the engagement repository."""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

from src.infrastructure.candidates.service import CandidateService
from src.infrastructure.mcp.artifact_mcp.context import resolve_repo_roots
from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, LOCAL_WRITE, READ_ONLY


def _service(repo_root: str | None) -> CandidateService:
    return CandidateService(
        resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)[0]
    )


def change_set_list(repo_root: str | None = None) -> dict[str, Any]:
    """List candidate architectures by id, name, state and parent."""
    return {"candidates": _service(repo_root).list()}


def change_set_read(
    artifact_id: str,
    mode: Literal["record", "standing", "diff"] = "record",
    base: str = "model",
    naive: str | None = None,
    diagram: str | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Read a candidate, its operation standing, or its scoped diff with optional diagram geometry."""
    service = _service(repo_root)
    if mode == "diff":
        return service.compare(artifact_id, base, naive, diagram)
    if mode == "standing":
        return service.standing(artifact_id)
    return service.read(artifact_id)


def change_set_create(
    record: dict[str, Any], diagram: str | None = None, repo_root: str | None = None
) -> dict[str, Any]:
    """Create an engagement candidate with a name and optional parent, scope, operations or scope diagram."""
    return _service(repo_root).create(record, diagram)


def change_set_edit(
    artifact_id: str, based_on: str, patch: dict[str, Any], repo_root: str | None = None
) -> dict[str, Any]:
    """Patch the named candidate fields using the version returned by the last read."""
    return _service(repo_root).edit(artifact_id, based_on, patch)


def change_set_check(candidates: list[str], repo_root: str | None = None) -> dict[str, Any]:
    """Check candidates offered for integration and identify the parties to each conflict."""
    return _service(repo_root).check(candidates)


def analysis_progress(artifact_id: str, kinds: list[str] | None = None, repo_root: str | None = None) -> dict[str, Any]:
    """Read outstanding analysis work and coverage, including unused categories from kinds."""
    return _service(repo_root).progress(artifact_id, kinds or ())


def analysis_incidence(artifact_id: str, repo_root: str | None = None) -> dict[str, Any]:
    """Read stressors, missing subjects and hits, end states, adaptations and pairwise coupling."""
    return _service(repo_root).incidence(artifact_id)


def register_candidate_read_tools(mcp: MCPServer) -> None:
    for tool in (change_set_list, change_set_read, change_set_check, analysis_progress, analysis_incidence):
        mcp.tool(
            name=tool.__name__,
            title=tool.__name__.replace("_", " ").title(),
            description=tool.__doc__,
            annotations=READ_ONLY,
            structured_output=True,
        )(tool)


def register_candidate_write_tools(mcp: MCPServer) -> None:
    for tool in (change_set_create, change_set_edit):
        register_mutation_tool(
            mcp,
            tool,
            name=tool.__name__,
            title=tool.__name__.replace("_", " ").title(),
            description=tool.__doc__ or "",
            annotations=LOCAL_WRITE if tool is change_set_create else DESTRUCTIVE_LOCAL_WRITE,
        )
