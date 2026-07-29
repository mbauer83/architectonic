"""Shared imports and helpers for MCP write submodules."""

from src.infrastructure.mcp.artifact_mcp.context import (
    RepoPreset,
    authoritative_callbacks_for,
    clear_caches_for_repo,
    mutation_context_for,
    registry_cached,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.write import artifact_write_ops

__all__ = [
    "DiagramConnectionInferenceMode",
    "RepoPreset",
    "WriteRepoScope",
    "_out",
    "authoritative_callbacks_for",
    "artifact_write_ops",
    "clear_caches_for_repo",
    "mutation_context_for",
    "registry_cached",
    "repo_cached",
    "resolve_repo_roots",
    "roots_key",
    "verifier_for",
]

WriteRepoScope = artifact_write_ops.WriteRepoScope
DiagramConnectionInferenceMode = artifact_write_ops.DiagramConnectionInferenceMode


def _out(result, *, dry_run: bool, include_content: bool | None = None) -> dict[str, object]:
    out: dict[str, object] = {
        "dry_run": dry_run,
        "wrote": bool(result.wrote),
        "path": str(result.path),
        "artifact_id": result.artifact_id,
        "verification": result.verification,
    }
    show_content = dry_run if include_content is None else include_content
    if show_content and result.content is not None:
        out["content"] = result.content
    if result.warnings:
        out["warnings"] = result.warnings
    return out
