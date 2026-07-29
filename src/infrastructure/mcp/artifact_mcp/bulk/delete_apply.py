"""Apply helpers for staged bulk delete execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.mcp.artifact_mcp.write._common import _out
from src.infrastructure.write import artifact_write_ops

from .common import strip_content


def apply_implicit_connection_deletes(
    *,
    implicit_connection_deletes: list[tuple[str, str, str]],
    root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches,
) -> None:
    for src, conn_type, target in implicit_connection_deletes:
        artifact_write_ops.remove_connection(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            source_entity=src,
            target_entity=target,
            connection_type=conn_type,
            dry_run=False,
        )


def apply_planned_deletes(
    *,
    planned: list[dict[str, Any]],
    root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    registry_factory: Callable[[], ArtifactRegistry] | None = None,
    verifier_factory: Callable[[ArtifactRegistry], ArtifactVerifier] | None = None,
    clear_repo_caches,
    operation_id: str,
    results: dict[int, dict[str, object]],
) -> bool:
    skipped = False
    for step in planned:
        index = int(step["index"])
        item = step["item"]
        op = str(item.get("op", ""))
        if skipped:
            results[index] = skipped_delete_result(op, operation_id=operation_id)
            continue
        try:
            if registry_factory is not None:
                registry = registry_factory()
                verifier = verifier_factory(registry) if verifier_factory is not None else verifier
            result = apply_single_delete(
                item=item,
                op=op,
                root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=clear_repo_caches,
            )
            out = strip_content(_out(result, dry_run=False))
            out["op"] = op
            out["operation_id"] = operation_id
            results[index] = out
        except Exception as exc:  # noqa: BLE001
            results[index] = {
                "op": op,
                "error": str(exc),
                "wrote": False,
                "dry_run": False,
                "operation_id": operation_id,
            }
            skipped = True
    return skipped


def apply_single_delete(
    *,
    item: dict[str, Any],
    op: str,
    root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches,
):
    if op == "delete_connection":
        return artifact_write_ops.remove_connection(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            source_entity=str(item["source_entity"]),
            target_entity=str(item["target_entity"]),
            connection_type=str(item["connection_type"]),
            dry_run=False,
        )
    if op == "delete_diagram":
        return artifact_write_ops.delete_diagram(
            repo_root=root,
            clear_repo_caches=clear_repo_caches,
            artifact_id=str(item["artifact_id"]),
            dry_run=False,
            verifier=verifier,
        )
    if op == "delete_document":
        return artifact_write_ops.delete_document(
            repo_root=root,
            clear_repo_caches=clear_repo_caches,
            artifact_id=str(item["artifact_id"]),
            dry_run=False,
            verifier=verifier,
        )
    return artifact_write_ops.delete_entity(
        repo_root=root,
        registry=registry,
        clear_repo_caches=clear_repo_caches,
        artifact_id=str(item["artifact_id"]),
        ignore_diagram_refs=True,
        dry_run=False,
    )


def serialize_connections(connections: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [
        {
            "source_entity": src,
            "connection_type": conn_type,
            "target_entity": target,
        }
        for src, conn_type, target in connections
    ]


def skipped_delete_result(op: str, *, operation_id: str) -> dict[str, object]:
    return {
        "op": op,
        "error": "Skipped because an earlier delete operation failed",
        "wrote": False,
        "dry_run": False,
        "operation_id": operation_id,
    }


def mark_delete_verification_failure(
    *,
    results: dict[int, dict[str, object]],
    items: list[dict[str, Any]],
    dry_run: bool,
    operation_id: str,
) -> None:
    for index, item in enumerate(items):
        existing = results.get(index)
        if existing is None:
            results[index] = {
                "op": str(item.get("op", "unknown")),
                "error": "Batch verification failed before commit",
                "wrote": False,
                "dry_run": dry_run,
                "operation_id": operation_id,
            }
        elif "error" not in existing:
            existing["error"] = "Batch verification failed before commit"
