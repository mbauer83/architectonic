"""Shared helpers for bulk MCP write/delete operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from src.application.verification.artifact_verifier import ArtifactRegistry
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp.artifact_mcp.edit_tools import _require_registry, _resolve
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

from .candidate_inventory import CandidateInventoryPort
from .candidate_state import candidate_registry

KNOWN_DELETE_OPS = frozenset({"delete_entity", "delete_connection", "delete_document", "delete_diagram"})
KNOWN_OPS = frozenset({"create_entity", "add_connection", "edit_entity", "edit_connection"})

#: The fields each op accepts, so an item carrying anything else is refused rather than performed
#: differently. A field this table does not name is a caller error — a misspelling, or a field
#: borrowed from a sibling tool — and ignoring it silently is how `edit_connection` with `mode:
#: "remove"` (the field is `operation`) ran as an *update* and reported `wrote: true` for a removal
#: that never happened. `_ref` is accepted everywhere: it is the caller's own alias for the item.
KNOWN_ITEM_FIELDS: dict[str, frozenset[str]] = {
    "create_entity": frozenset({
        "op", "_ref", "artifact_type", "name", "summary", "properties", "attribute_types", "notes",
        "keywords", "specializations", "artifact_id", "version", "status", "group",
    }),
    "add_connection": frozenset({
        "op", "_ref", "source_entity", "target_entity", "connection_type", "description",
        "src_multiplicity", "tgt_multiplicity", "specializations", "metadata", "version", "status",
    }),
    "edit_entity": frozenset({
        "op", "_ref", "artifact_id", "name", "summary", "properties", "attribute_types", "notes",
        "keywords", "specializations", "version", "status", "group",
    }),
    "edit_connection": frozenset({
        "op", "_ref", "source_entity", "target_entity", "connection_type", "operation",
        "description", "src_multiplicity", "tgt_multiplicity", "specializations", "metadata",
    }),
}


def unknown_item_fields(item: dict) -> tuple[str, ...]:
    """The fields *item* carries that its op does not accept, in the order they appear."""
    accepted = KNOWN_ITEM_FIELDS.get(str(item.get("op", "")))
    if accepted is None:
        return ()
    return tuple(str(key) for key in item if str(key) not in accepted)


def resolve_ref(value: str, ref_map: dict[str, str]) -> str:
    if value.startswith("$ref:"):
        key = value[5:]
        resolved = ref_map.get(key)
        if resolved is None:
            raise ValueError(f"Unresolved $ref '{key}' — no create_entity item with _ref='{key}' succeeded")
        return resolved
    return value


def strip_content(result: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in result.items() if key != "content"}


def resolve_root(repo_root: str | None) -> Path:
    root, _registry, _verifier = _resolve(repo_root, need_registry=False)
    return root


def local_apply_paths(repo_root: Path, paths: list[Path]) -> None:
    from src.infrastructure.artifact_index import mutable_artifact_index

    mutable_artifact_index(repo_root).apply_file_changes(paths)


def temp_repo_callbacks(
    repo_root: Path,
) -> tuple[Callable[[Path], None], set[Path]]:
    changed_paths: set[Path] = set()

    def clear_repo_caches(path: Path) -> None:
        changed_paths.add(path.resolve())
        local_apply_paths(repo_root, [path])

    return clear_repo_caches, changed_paths


def map_path_to_live(path_value: object, *, staged_root: Path, live_root: Path) -> object:
    if not isinstance(path_value, str):
        return path_value
    path = Path(path_value)
    try:
        rel = path.relative_to(staged_root)
    except ValueError:
        return path_value
    return str(live_root / rel)


def normalize_staged_result(
    result: dict[str, object],
    *,
    staged_root: Path,
    live_root: Path,
    dry_run: bool,
    committed: bool,
) -> dict[str, object]:
    out = dict(result)
    if "path" in out:
        out["path"] = map_path_to_live(out["path"], staged_root=staged_root, live_root=live_root)
    if dry_run or not committed:
        out["wrote"] = False
    out.pop("dry_run", None)
    # Strip per-item verification when passing — batch-level verification covers this
    verification = out.get("verification")
    if isinstance(verification, dict) and verification.get("valid") and not verification.get("issues"):
        del out["verification"]
    return out


def normalize_staged_verification(
    verification: dict[str, object],
    *,
    staged_root: Path,
    live_root: Path,
) -> dict[str, object]:
    out = dict(verification)
    out["repo_root"] = str(live_root)
    raw_results = out.get("results", [])
    results = raw_results if isinstance(raw_results, list) else []
    out["results"] = [
        {
            **result,
            "path": map_path_to_live(
                result.get("path"),
                staged_root=staged_root,
                live_root=live_root,
            ),
        }
        for result in results
        if isinstance(result, dict)
    ]
    return out


def _verification_payload(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    results: list,
    executed: bool,
    preexisting_invalid_paths: set[Path] | None = None,
) -> dict[str, object]:
    invalid = [result for result in results if not result.valid]
    # When preexisting_invalid_paths is provided, neighbour files whose invalidity
    # predates this batch are non-blocking.  Only files that are newly invalid
    # (i.e. not already broken in the live repo) block the commit.
    if preexisting_invalid_paths is not None:
        blocking_invalid = [result for result in invalid if result.path.resolve() not in preexisting_invalid_paths]
    else:
        blocking_invalid = invalid
    return {
        "valid": not blocking_invalid,
        "executed": executed,
        "counts": {
            "files": len(results),
            "valid_files": sum(1 for result in results if result.valid),
            "invalid_files": len(invalid),
            "errors": sum(len(result.errors) for result in results),
            "warnings": sum(len(result.warnings) for result in results),
        },
        "results": [
            {
                "path": str(result.path),
                "file_type": result.file_type,
                "valid": result.valid,
                "issues": [
                    {
                        "severity": issue.severity,
                        "code": issue.code,
                        "message": issue.message,
                        "location": issue.location,
                    }
                    for issue in result.issues
                ],
            }
            for result in invalid
        ],
        "repo_root": str(repo_root),
        "registry_entities": len(registry.entity_ids()),
    }


_PUML_SYNTAX_CODES: frozenset[str] = frozenset({"E350", "W350", "W351", "W352"})


def _preexisting_invalid_paths(
    *,
    invalid_neighbor_staged_results: list,
    staged_root: Path,
    live_root: Path,
) -> set[Path]:
    """Return the subset of invalid neighbour staged paths whose invalidity
    predates this batch (i.e. they were already invalid in the live repo).

    Performance contract: no PlantUML subprocess is spawned.

    Strategy per neighbour file:
    1. Map staged path → live path.  If live path does not exist the file is
       new (batch created it) → not pre-existing.
    2. Re-verify the live file without the PlantUML syntax check (pure
       structural/reference rules, all in-process).
       - If the live result is invalid → pre-existing regardless of cause.
       - If the live result is valid, inspect the *staged* issues:
         · If every staged issue has a PlantUML syntax code (E350/W350/W351/
           W352) the file body was already broken before the batch — the batch
           never rewrites neighbour diagram bodies — so it is pre-existing.
         · Otherwise at least one staged issue is a reference/structural error
           that didn't exist in the live repo, meaning the batch caused it →
           not pre-existing → blocking.
    """
    if not invalid_neighbor_staged_results:
        return set()

    from src.application.verification._verifier_inventory import inventory_files

    live_registry = ArtifactRegistry(shared_artifact_index([live_root]))
    # check_puml_syntax=False: avoid spawning any subprocess in this path.

    live_verifier = build_artifact_verifier(
        live_registry, check_puml_syntax=False, catalogs=process_runtime_catalogs()
    )
    # Build the live inventory once to get authoritative file-type mappings.
    live_inv = inventory_files(live_root, include_diagrams=True)

    staged_root_resolved = staged_root.resolve()
    preexisting: set[Path] = set()

    for staged_result in invalid_neighbor_staged_results:
        staged_path = staged_result.path
        try:
            rel = staged_path.resolve().relative_to(staged_root_resolved)
        except ValueError:
            continue
        live_path = (live_root / rel).resolve()
        if not live_path.exists():
            # File is new — created by this batch.  Never pre-existing.
            continue
        rel_str = str(rel)
        file_type = live_inv.file_type_by_relpath.get(rel_str)
        if file_type is None:
            # Not tracked (e.g. a docs/ file); cannot determine — skip.
            continue
        if file_type == "entity":
            live_result = live_verifier.verify_entity_file(live_path)
        elif file_type == "connection":
            live_result = live_verifier.verify_connection_file(live_path)
        else:
            live_result = live_verifier.verify_diagram_file(live_path)

        if not live_result.valid:
            # Already broken in live repo → pre-existing.
            preexisting.add(staged_path.resolve())
        elif all(issue.code in _PUML_SYNTAX_CODES for issue in staged_result.issues):
            # Live structural/reference checks pass, but the staged result has
            # only PlantUML syntax issues.  The batch never rewrites diagram
            # bodies, so those syntax errors were already in the file →
            # pre-existing.
            preexisting.add(staged_path.resolve())
        # else: live is valid but staged has non-syntax errors → batch caused
        # them → blocking (do not add to preexisting).

    return preexisting


def stage_batch_verification(
    repo_root: Path,
    *,
    changed_paths: set[Path],
    directly_changed_paths: set[Path] | None = None,
    live_root: Path | None = None,
) -> dict[str, object]:

    registry = (
        candidate_registry(live_root=live_root, staged_root=repo_root, touched_paths=changed_paths)
        if live_root is not None
        else ArtifactRegistry(shared_artifact_index([repo_root]))
    )
    inventory = (
        CandidateInventoryPort(registry=registry, changed_paths=changed_paths)
        if live_root is not None
        else None
    )
    verifier = build_artifact_verifier(
        registry,
        catalogs=process_runtime_catalogs(),
        file_inventory=inventory,
    )
    results = verifier.verify_paths(
        repo_root,
        changed_paths=sorted(changed_paths),
        verification_scope="impacted",
        include_diagrams=True,
    )

    preexisting: set[Path] | None = None
    if directly_changed_paths is not None and live_root is not None:
        # Identify invalid neighbour files — those not directly written by this
        # batch.  For each, check whether they were already invalid before the
        # batch by re-verifying against the live repo.
        directly_changed_resolved = {p.resolve() for p in directly_changed_paths}
        invalid_neighbor_results = [
            result for result in results if not result.valid and result.path.resolve() not in directly_changed_resolved
        ]
        preexisting = _preexisting_invalid_paths(
            invalid_neighbor_staged_results=invalid_neighbor_results,
            staged_root=repo_root,
            live_root=live_root,
        )

    return _verification_payload(
        repo_root=repo_root,
        registry=registry,
        results=results,
        executed=True,
        preexisting_invalid_paths=preexisting,
    )


def batch_verification(
    repo_root: str | None,
    *,
    dry_run: bool,
    executed: bool,
    changed_paths: list[Path] | None = None,
    verification_scope: Literal["changed", "impacted", "full"] = "full",
) -> dict[str, object]:
    if dry_run or not executed:
        return {
            "valid": True,
            "executed": False,
            "counts": {"files": 0, "valid_files": 0, "invalid_files": 0, "errors": 0, "warnings": 0},
            "results": [],
        }

    root, registry, verifier = _resolve(repo_root, need_registry=True)
    registry = _require_registry(registry)
    if changed_paths and verification_scope in {"changed", "impacted"}:
        results = verifier.verify_paths(
            root,
            changed_paths=changed_paths,
            verification_scope=verification_scope,
            include_diagrams=True,
        )
    else:
        results = verifier.verify_all(root, include_diagrams=True)
    return _verification_payload(
        repo_root=root,
        registry=registry,
        results=results,
        executed=True,
    )
