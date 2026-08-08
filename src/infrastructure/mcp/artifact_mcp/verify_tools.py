from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS, DOCS
from src.infrastructure.mcp.artifact_mcp.context import RepoScope, resolve_repo_roots, roots_key, verifier_for
from src.infrastructure.mcp.artifact_mcp.formatting import as_issue_dict, as_verification_result_dict
from src.infrastructure.mcp.artifact_mcp.tool_annotations import READ_ONLY


def artifact_verify(
    path: str | None = None,
    *,
    file_type: Literal["entity", "connection", "diagram", "document"] | None = None,
    include_diagrams: bool = True,
    return_mode: Literal["summary", "full"] = "summary",
    confirm_full_pass: bool = False,
    repo_root: str | None = None,
    repo_scope: RepoScope = "both",
) -> dict[str, Any]:
    roots = resolve_repo_roots(
        repo_scope=repo_scope,
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    key = roots_key(roots)
    engagement_root = roots[0]
    verifier = verifier_for(key, include_registry=True)

    if path is not None:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = engagement_root / p
        inferred = file_type
        if inferred is None:
            if p.suffix == ".puml" or (p.suffix == ".md" and DIAGRAM_CATALOG in p.parts and DIAGRAMS in p.parts):
                inferred = "diagram"
            elif p.suffix == ".md" and DOCS in p.parts:
                inferred = "document"
            else:
                inferred = "connection" if "connections" in p.parts else "entity"
        match inferred:
            case "entity":
                result = verifier.verify_entity_file(p)
            case "connection":
                result = verifier.verify_connection_file(p)
            case "diagram":
                result = (
                    verifier.verify_matrix_diagram_file(p) if p.suffix == ".md" else verifier.verify_diagram_file(p)
                )
            case "document":
                result = verifier.verify_document_file(p)
        out = as_verification_result_dict(result)
        out["repo_roots"] = [str(r) for r in roots]
        out["repo_scope"] = repo_scope
        return out

    # A full pass re-verifies every file and takes minutes on a cold cache. Answering that with
    # silence cost an operator a 30-minute client timeout and a backend that looked hung; answering
    # it with the reason costs milliseconds. `ARCH_MODEL_VERIFY_MODE=full` is consent already, so
    # `pending_full_pass_reason` returns None under it and CI is unaffected.
    if not confirm_full_pass:
        pending = {
            str(root): reason
            for root in roots
            if (reason := verifier.pending_full_pass_reason(root, include_diagrams=include_diagrams))
        }
        if pending:
            return {
                "repo_roots": [str(r) for r in roots],
                "repo_scope": repo_scope,
                "include_diagrams": include_diagrams,
                "pass_mode": {root: "full-required" for root in pending},
                "full_pass_required": pending,
                "files_to_verify": {
                    root: verifier.count_verifiable_files(Path(root), include_diagrams=include_diagrams)
                    for root in pending
                },
                "message": (
                    "A full pass is required and was not confirmed. It re-verifies every file and "
                    "takes minutes on a cold cache. Re-call with confirm_full_pass=true, or set "
                    "ARCH_MODEL_VERIFY_MODE=full for callers that cannot confirm."
                ),
                "results": [],
            }

    # Batch verify: every resolved root — the description promises repo_scope
    # "both", and answering for the engagement repo alone under that contract
    # silently under-reported enterprise-side errors.
    results = []
    pass_modes: dict[str, str] = {}
    for root in roots:
        mode, root_results = verifier.verify_all_reporting_pass_mode(root, include_diagrams=include_diagrams)
        pass_modes[str(root)] = mode
        results.extend(root_results)
    total = len(results)
    total_valid = sum(1 for r in results if r.valid)
    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    files_by_type: dict[str, int] = {}
    for r in results:
        files_by_type[r.file_type] = files_by_type.get(r.file_type, 0) + 1
    if return_mode == "full":
        payload: Any = [as_verification_result_dict(r) for r in results if r.issues]
    else:
        payload = [
            {
                "path": str(r.path),
                "file_type": r.file_type,
                "valid": r.valid,
                "issues": [as_issue_dict(i) for i in r.issues],
            }
            for r in results
            if r.issues
        ]
    return {
        "repo_roots": [str(r) for r in roots],
        "repo_scope": repo_scope,
        "include_diagrams": include_diagrams,
        # Which pass answered, per root: "full" re-verified every file (minutes on a cold
        # cache), "incremental-cached" returned stored results, "incremental" verified only
        # what changed. Reported so a caller can tell a first-run cost from a hang.
        "pass_mode": pass_modes,
        "counts": {
            # files = every artifact file the verifier enumerated across all model roots
            # (legacy model/ + every projects/<slug>/model/), diagrams and documents.
            # files_by_type breaks that total down so the number's meaning is explicit.
            "files": total,
            "files_by_type": files_by_type,
            "valid_files": total_valid,
            "invalid_files": total - total_valid,
            "errors": total_errors,
            "warnings": total_warnings,
        },
        "results": payload,
    }


# Keep the original functions as thin aliases for direct callers / tests.
def artifact_verify_file(
    path: str,
    *,
    file_type: Literal["entity", "connection", "diagram", "document"] | None = None,
    repo_root: str | None = None,
    repo_scope: RepoScope = "both",
) -> dict[str, Any]:
    return artifact_verify(
        path,
        file_type=file_type,
        repo_root=repo_root,
        repo_scope=repo_scope,
    )


def artifact_verify_all(
    *,
    include_diagrams: bool = True,
    return_mode: Literal["summary", "full"] = "summary",
    confirm_full_pass: bool = False,
    repo_root: str | None = None,
    repo_scope: RepoScope = "both",
) -> dict[str, Any]:
    return artifact_verify(
        include_diagrams=include_diagrams,
        return_mode=return_mode,
        repo_root=repo_root,
        repo_scope=repo_scope,
    )


def register_verify_tools(mcp: FastMCP) -> None:
    mcp.tool(
        name="artifact_verify",
        title="Artifact Verifier",
        description=(
            "Verify one file or all model files. "
            "Pass path= to verify a single entity/connection/diagram file "
            "(absolute or relative to repo_root; "
            "file_type is inferred if omitted). "
            "Omit path to verify the entire repository — returns issue "
            "counts and a list of files with errors/warnings. "
            "return_mode='summary' (default) gives compact issue lines; 'full' gives per-issue detail."
            "\n\nRepo selection: repo_scope defaults to both (engagement + enterprise)."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )(artifact_verify)
