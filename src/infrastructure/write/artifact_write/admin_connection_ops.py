"""Admin-mode connection writes (enterprise repo). See admin_ops for the boundary contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.modeling.artifact_write import format_outgoing_markdown
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.artifact_id import stable_id

from .boundary import assert_enterprise_write_root, modification_stamp
from .connection import (
    _build_content as _build_conn_content,
)
from .connection import (
    _resolve_outgoing_path,
    _rollback,
    _validate_inputs,
    verification_to_conn_dict,
)
from .connection import (
    _write_and_verify as _write_and_verify_conn,
)
from .parse_existing import ParsedOutgoing, parse_outgoing_file
from .types import WriteResult

__all__ = ["admin_add_connection", "admin_remove_connection"]


def admin_add_connection(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    source_entity: str,
    connection_type: str,
    target_entity: str,
    description: str | None,
    version: str,
    status: str,
    last_updated: str | None,
    dry_run: bool,
) -> WriteResult:
    assert_enterprise_write_root(repo_root)
    _validate_inputs(registry, connection_type, source_entity, target_entity)

    outgoing_path = _resolve_outgoing_path(registry, source_entity)
    conn_id = f"{connection_type} → {target_entity}"
    content = _build_conn_content(
        outgoing_path, source_entity, connection_type, target_entity,
        description, version, status, last_updated or modification_stamp(),
    )

    if dry_run:
        return WriteResult(
            wrote=False, path=outgoing_path, artifact_id=conn_id, content=content, warnings=[], verification=None
        )

    result = _write_and_verify_conn(
        outgoing_path, content, verifier, source_entity, connection_type, target_entity
    )
    if result.wrote:
        clear_repo_caches(outgoing_path)
    return result


def _format_remaining(source_entity: str, parsed: ParsedOutgoing, remaining: list[dict[str, object]]) -> str:
    return format_outgoing_markdown(
        source_entity=source_entity,
        version=str(parsed.frontmatter.get("version", "0.1.0")),
        status=str(parsed.frontmatter.get("status", "active")),
        last_updated=modification_stamp(),
        connections=remaining,
    )


def admin_remove_connection(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    source_entity: str,
    target_entity: str,
    connection_type: str,
    dry_run: bool,
) -> WriteResult:
    assert_enterprise_write_root(repo_root)
    outgoing_path = _resolve_outgoing_path(registry, source_entity)
    if not outgoing_path.exists():
        raise ValueError(f"No outgoing file for '{source_entity}'")

    parsed = parse_outgoing_file(outgoing_path)
    conn_id = f"{connection_type} -> {target_entity}"
    remaining = [
        c
        for c in parsed.connections
        if not (
            c["connection_type"] == connection_type
            and stable_id(str(c["target_entity"])) == stable_id(target_entity)
        )
    ]
    if len(remaining) == len(parsed.connections):
        raise ValueError(f"Connection '{conn_id}' not found in {outgoing_path.name}")
    deletes_file = not remaining

    if dry_run:
        content = (
            "(file would be deleted — last connection removed)"
            if deletes_file
            else _format_remaining(source_entity, parsed, remaining)
        )
        return WriteResult(
            wrote=False, path=outgoing_path, artifact_id=conn_id, content=content, warnings=[], verification=None
        )

    if deletes_file:
        outgoing_path.unlink()
        clear_repo_caches(outgoing_path)
        return WriteResult(
            wrote=True, path=outgoing_path, artifact_id=conn_id, content=None,
            warnings=["Deleted empty .outgoing.md file"],
            verification={"path": str(outgoing_path), "file_type": "connection", "valid": True, "issues": []},
        )

    content = _format_remaining(source_entity, parsed, remaining)
    prev = outgoing_path.read_text(encoding="utf-8")
    outgoing_path.write_text(content, encoding="utf-8")
    res = verifier.verify_outgoing_file(outgoing_path)
    vdict = verification_to_conn_dict(outgoing_path, res)
    if not res.valid:
        _rollback(outgoing_path, prev)
        return WriteResult(
            wrote=False, path=outgoing_path, artifact_id=conn_id, content=content, warnings=[], verification=vdict
        )
    clear_repo_caches(outgoing_path)
    return WriteResult(
        wrote=True, path=outgoing_path, artifact_id=conn_id, content=None, warnings=[], verification=vdict
    )
