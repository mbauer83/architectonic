"""Execution helpers for staged bulk-write operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.context import expand_artifact_id
from src.infrastructure.mcp.artifact_mcp.write._common import _out
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write import artifact_write_ops
from src.infrastructure.write.artifact_write.connection_edit import _UNSET as _CONN_UNSET
from src.infrastructure.write.artifact_write.entity_edit import _UNSET as _ENTITY_UNSET

from .common import resolve_ref, strip_content


def skipped_result(op: str, *, dry_run: bool, operation_id: str) -> dict[str, object]:
    return {
        "op": op,
        "error": "Skipped because an earlier batch item failed",
        "wrote": False,
        "dry_run": dry_run,
        "operation_id": operation_id,
    }


def error_result(
    op: str,
    exc: Exception,
    *,
    dry_run: bool,
    operation_id: str,
) -> dict[str, object]:
    return {
        "op": op,
        "error": str(exc),
        "wrote": False,
        "dry_run": dry_run,
        "operation_id": operation_id,
    }


def apply_create_entities(
    creates_ent: list[tuple[int, dict[str, Any]]],
    *,
    ref_map: dict[str, str],
    results: dict[int, dict[str, object]],
    clear_repo_caches: Callable[[Path], None],
    staged_root: Path,
    dry_run: bool,
    operation_id: str,
) -> bool:
    skipped = False
    for index, item in creates_ent:
        ref = item.get("_ref")
        if skipped:
            results[index] = skipped_result("create_entity", dry_run=dry_run, operation_id=operation_id)
            continue
        try:
            from src.domain.repository.groups import UNCATEGORIZED  # noqa: PLC0415

            result = artifact_write_ops.create_entity(
                repo_root=staged_root,
                verifier=build_artifact_verifier(None, catalogs=process_runtime_catalogs()),
                clear_repo_caches=clear_repo_caches,
                artifact_type=item["artifact_type"],
                name=item["name"],
                summary=item.get("summary"),
                properties=item.get("properties"),
                attribute_types=item.get("attribute_types"),
                notes=item.get("notes"),
                keywords=item.get("keywords"),
                specializations=item.get("specializations"),
                artifact_id=item.get("artifact_id"),
                version=item.get("version", "0.1.0"),
                status=item.get("status", "draft"),
                group=item.get("group") or UNCATEGORIZED,
                last_updated=None,
                dry_run=False,
            )
            out = strip_content(_out(result, dry_run=False))
            out["op"] = "create_entity"
            results[index] = out
            if ref:
                ref_map[ref] = str(out["artifact_id"])
            skipped = skipped or not result.wrote
        except Exception as exc:  # noqa: BLE001
            results[index] = error_result("create_entity", exc, dry_run=dry_run, operation_id=operation_id)
            skipped = True
    return skipped


def apply_add_connections(
    creates_con: list[tuple[int, dict[str, Any]]],
    *,
    ref_map: dict[str, str],
    results: dict[int, dict[str, object]],
    clear_repo_caches: Callable[[Path], None],
    staged_root: Path,
    dry_run: bool,
    operation_id: str,
    skipped: bool,
    current_registry: Callable[[], ArtifactRegistry],
) -> bool:
    for index, item in creates_con:
        if skipped:
            results[index] = skipped_result("add_connection", dry_run=dry_run, operation_id=operation_id)
            continue
        try:

            source = resolve_ref(item["source_entity"], ref_map)
            target = resolve_ref(item["target_entity"], ref_map)
            registry = current_registry()
            verifier = build_artifact_verifier(registry, catalogs=process_runtime_catalogs())
            result = artifact_write_ops.add_connection(
                repo_root=staged_root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=clear_repo_caches,
                source_entity=source,
                connection_type=item["connection_type"],
                target_entity=target,
                description=item.get("description"),
                src_multiplicity=item.get("src_multiplicity"),
                tgt_multiplicity=item.get("tgt_multiplicity"),
                specializations=item.get("specializations"),
                metadata=item.get("metadata"),
                version=item.get("version", "0.1.0"),
                status=item.get("status", "draft"),
                last_updated=None,
                dry_run=False,
            )
            out = strip_content(_out(result, dry_run=False))
            out["op"] = "add_connection"
            results[index] = out
            skipped = skipped or not result.wrote
        except Exception as exc:  # noqa: BLE001
            results[index] = error_result("add_connection", exc, dry_run=dry_run, operation_id=operation_id)
            skipped = True
    return skipped


def apply_edits(
    edits: list[tuple[int, dict[str, Any]]],
    *,
    results: dict[int, dict[str, object]],
    clear_repo_caches: Callable[[Path], None],
    staged_root: Path,
    dry_run: bool,
    operation_id: str,
    skipped: bool,
    current_registry: Callable[[], ArtifactRegistry],
) -> bool:
    for index, item in edits:
        op = str(item.get("op", ""))
        if skipped:
            results[index] = skipped_result(op, dry_run=dry_run, operation_id=operation_id)
            continue
        try:

            registry = current_registry()
            verifier = build_artifact_verifier(registry, catalogs=process_runtime_catalogs())
            result = _apply_single_edit(
                item=item,
                op=op,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=clear_repo_caches,
                staged_root=staged_root,
            )
            out = strip_content(_out(result, dry_run=False))
            out["op"] = op
            results[index] = out
            skipped = skipped or not result.wrote
        except Exception as exc:  # noqa: BLE001
            results[index] = error_result(op, exc, dry_run=dry_run, operation_id=operation_id)
            skipped = True
    return skipped


def _apply_single_edit(
    *,
    item: dict[str, Any],
    op: str,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    staged_root: Path,
):
    if op == "edit_entity":
        return artifact_write_ops.edit_entity(
            repo_root=staged_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            artifact_id=expand_artifact_id(registry, str(item["artifact_id"])),
            name=item.get("name"),
            summary=item["summary"] if "summary" in item else _ENTITY_UNSET,
            properties=item["properties"] if "properties" in item else _ENTITY_UNSET,
            attribute_types=item["attribute_types"] if "attribute_types" in item else _ENTITY_UNSET,
            notes=item["notes"] if "notes" in item else _ENTITY_UNSET,
            keywords=item["keywords"] if "keywords" in item else _ENTITY_UNSET,
            specializations=item["specializations"] if "specializations" in item else _ENTITY_UNSET,
            version=item.get("version"),
            status=item.get("status"),
            group=item.get("group"),
            dry_run=False,
        )
    source_entity = expand_artifact_id(registry, str(item["source_entity"]))
    target_entity = expand_artifact_id(registry, str(item["target_entity"]))
    if item.get("operation", "update") == "remove":
        return artifact_write_ops.remove_connection(
            repo_root=staged_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            source_entity=source_entity,
            target_entity=target_entity,
            connection_type=item["connection_type"],
            dry_run=False,
        )
    return artifact_write_ops.edit_connection(
        repo_root=staged_root,
        registry=registry,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        source_entity=source_entity,
        target_entity=target_entity,
        connection_type=item["connection_type"],
        description=item.get("description"),
        src_multiplicity=item["src_multiplicity"] if "src_multiplicity" in item else _CONN_UNSET,
        tgt_multiplicity=item["tgt_multiplicity"] if "tgt_multiplicity" in item else _CONN_UNSET,
        dry_run=False,
    )
