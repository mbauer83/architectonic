"""Connection editing and removal operations."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from src.application.modeling.artifact_write import format_outgoing_markdown
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.specialization_values import (
    applied_specialization_slugs,
)

from .boundary import assert_engagement_write_root, modification_stamp
from .coerce import as_optional_str_list
from .connection import _assert_pair_writable, _resolve_outgoing_path, _rollback, verification_to_conn_dict
from .types import WriteResult

_UNSET = object()


def _set_specialization(conn: dict[str, object], applied: Sequence[str]) -> None:
    """Write the applied specialization set onto a parsed connection dict: a scalar for one
    (byte-identical to existing files), a list for several (§15.2), removed for none."""
    if len(applied) == 1:
        conn["specialization"] = applied[0]
    elif applied:
        conn["specialization"] = list(applied)
    else:
        conn.pop("specialization", None)


def edit_connection(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    source_entity: str,
    target_entity: str,
    connection_type: str,
    description: str | None | object = _UNSET,
    src_multiplicity: str | None | object = _UNSET,
    tgt_multiplicity: str | None | object = _UNSET,
    specializations: Sequence[str] | None | object = _UNSET,
    metadata: dict[str, object] | None | object = _UNSET,
    dry_run: bool,
) -> WriteResult:
    """Update an existing connection (description, multiplicities, and/or specializations).

    Identifies the connection by (source, target, type) triple.
    Rebuilds the .outgoing.md file with the updated fields — every other connection's dict
    (incl. its own specialization, if any) is carried through `parsed.connections`
    unmodified, so a sibling's metadata block round-trips byte-for-byte.
    Pass src_multiplicity="" or tgt_multiplicity="" to remove an existing multiplicity, or
    specializations=[] to remove them. ``metadata`` is PATCHED key by
    key (truly mirroring the entity edit API's `properties`): send only the keys you are
    changing, map a key to None to remove it, pass None for the whole parameter to clear
    every attribute. Omit (leave as _UNSET) to preserve the existing value.
    """
    assert_engagement_write_root(repo_root)
    outgoing_path = _resolve_outgoing_path(registry, source_entity)

    if not outgoing_path.exists():
        raise ValueError(f"No outgoing file for '{source_entity}'")

    from .parse_existing import parse_outgoing_file

    parsed = parse_outgoing_file(outgoing_path)

    # Find the target connection
    found = False
    for conn in parsed.connections:
        if _is_the_connection(conn, connection_type, target_entity):
            if description is not _UNSET:
                conn["description"] = str(description) if description else ""
            if src_multiplicity is not _UNSET:
                if src_multiplicity:
                    conn["src_multiplicity"] = str(src_multiplicity)
                else:
                    conn.pop("src_multiplicity", None)
            if tgt_multiplicity is not _UNSET:
                if tgt_multiplicity:
                    conn["tgt_multiplicity"] = str(tgt_multiplicity)
                else:
                    conn.pop("tgt_multiplicity", None)
            if specializations is not _UNSET:
                _set_specialization(conn, applied_specialization_slugs(specializations))
            if metadata is not _UNSET:
                # PATCH key by key, truly mirroring the entity edit API's `properties`:
                # only sent keys change, a None value removes its key, and None for the
                # whole parameter clears the mapping.
                if metadata is None:
                    conn.pop("metadata", None)
                elif isinstance(metadata, dict):
                    existing_md = conn.get("metadata")
                    merged_md = dict(existing_md) if isinstance(existing_md, dict) else {}
                    for meta_key, meta_value in metadata.items():
                        if meta_value is None:
                            merged_md.pop(str(meta_key), None)
                        else:
                            merged_md[str(meta_key)] = meta_value
                    if merged_md:
                        conn["metadata"] = merged_md
                    else:
                        conn.pop("metadata", None)
            found = True
            # One reader for the value's two shapes, shared with every other consumer.
            effective = applied_specialization_slugs(conn.get("specialization"))
            break

    if not found:
        raise ValueError(f"Connection '{connection_type} -> {target_entity}' not found in {outgoing_path.name}")

    # Gate on the effective post-merge specialization set: an edit that moves a connection
    # onto a quarantined pair must be refused just like an add.
    _assert_pair_writable(repo_root, connection_type, effective)

    content = format_outgoing_markdown(
        source_entity=source_entity,
        version=str(parsed.frontmatter.get("version", "0.1.0")),
        status=str(parsed.frontmatter.get("status", "draft")),
        last_updated=modification_stamp(),
        connections=parsed.connections,
    )
    conn_id = f"{connection_type} -> {target_entity}"

    if dry_run:
        return WriteResult(
            wrote=False,
            path=outgoing_path,
            artifact_id=conn_id,
            content=content,
            warnings=[],
            verification=None,
        )

    return _write_verify_clear(
        outgoing_path,
        content,
        verifier,
        conn_id,
        clear_repo_caches,
        repo_root,
    )


def _is_the_connection(conn: Mapping[str, object], connection_type: str, target_entity: str) -> bool:
    """Whether a recorded connection is the one a caller named.

    The type must match exactly; the target matches on its stable id, so an address that omits the
    slug — or carries a stale one after a rename — still names the same artifact. Written once
    because it was written four times in this module, and a predicate spelled four ways is how one
    of the spellings ends up meaning something slightly different.
    """
    return (
        conn["connection_type"] == connection_type
        and stable_id(str(conn["target_entity"])) == stable_id(target_entity)
    )


def _records_it(path: Path, connection_type: str, target_entity: str) -> bool:
    if not path.exists():
        return False
    from .parse_existing import parse_outgoing_file  # noqa: PLC0415

    return any(
        _is_the_connection(c, connection_type, target_entity)
        for c in parse_outgoing_file(path).connections
    )


def _endpoint_that_records_it(
    registry: ArtifactRegistry, source_entity: str, target_entity: str, connection_type: str
) -> tuple[str, str, Path]:
    """Which endpoint's file actually holds this connection, and the endpoints in that order.

    A symmetric relationship has no direction — the ontology says so, the index buckets it as
    `symmetric` under *both* endpoints, and creation admits it from either side. It is still written
    down once, in one endpoint's `.outgoing.md`, so naming it from the other end found nothing and
    reported it missing. An author deleting `B —— A` was told no such connection existed while it sat
    in A's file, and the only way through was to know which end had happened to record it.

    Directed relationships are untouched: `A -> B` and `B -> A` are different connections, and
    looking for one under the other would delete the wrong thing.
    """
    named = _resolve_outgoing_path(registry, source_entity)
    if _records_it(named, connection_type, target_entity):
        return source_entity, target_entity, named

    from src.infrastructure.app_bootstrap import process_runtime_catalogs  # noqa: PLC0415

    if not process_runtime_catalogs().connections.is_symmetric(connection_type):
        return source_entity, target_entity, named

    other = _resolve_outgoing_path(registry, target_entity)
    if _records_it(other, connection_type, source_entity):
        return target_entity, source_entity, other
    return source_entity, target_entity, named


def remove_connection(
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
    """Remove a connection from an .outgoing.md file.

    If this was the last connection, the .outgoing.md file is deleted.
    """
    assert_engagement_write_root(repo_root)
    source_entity, target_entity, outgoing_path = _endpoint_that_records_it(
        registry, source_entity, target_entity, connection_type
    )

    if not outgoing_path.exists():
        raise ValueError(f"No outgoing file for '{source_entity}'")

    from .parse_existing import parse_outgoing_file

    parsed = parse_outgoing_file(outgoing_path)
    conn_id = f"{connection_type} -> {target_entity}"

    original_count = len(parsed.connections)
    remaining = [
        c
        for c in parsed.connections
        if not _is_the_connection(c, connection_type, target_entity)
    ]

    if len(remaining) == original_count:
        raise ValueError(f"Connection '{conn_id}' not found in {outgoing_path.name}")

    if dry_run:
        if not remaining:
            return WriteResult(
                wrote=False,
                path=outgoing_path,
                artifact_id=conn_id,
                content="(file would be deleted — last connection removed)",
                warnings=[],
                verification=None,
            )
        content = format_outgoing_markdown(
            source_entity=source_entity,
            version=str(parsed.frontmatter.get("version", "0.1.0")),
            status=str(parsed.frontmatter.get("status", "draft")),
            last_updated=modification_stamp(),
            connections=remaining,
        )
        return WriteResult(
            wrote=False,
            path=outgoing_path,
            artifact_id=conn_id,
            content=content,
            warnings=[],
            verification=None,
        )

    # Real write
    if not remaining:
        outgoing_path.read_text(encoding="utf-8")
        outgoing_path.unlink()
        clear_repo_caches(outgoing_path)
        return WriteResult(
            wrote=True,
            path=outgoing_path,
            artifact_id=conn_id,
            content=None,
            warnings=["Deleted empty .outgoing.md file"],
            verification={
                "path": str(outgoing_path),
                "file_type": "connection",
                "valid": True,
                "issues": [],
            },
        )

    content = format_outgoing_markdown(
        source_entity=source_entity,
        version=str(parsed.frontmatter.get("version", "0.1.0")),
        status=str(parsed.frontmatter.get("status", "draft")),
        last_updated=modification_stamp(),
        connections=remaining,
    )

    return _write_verify_clear(
        outgoing_path,
        content,
        verifier,
        conn_id,
        clear_repo_caches,
        repo_root,
    )


def edit_connection_associations(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    source_entity: str,
    connection_type: str,
    target_entity: str,
    add_entities: list[str] | None = None,
    remove_entities: list[str] | None = None,
    dry_run: bool,
) -> WriteResult:
    """Add or remove second-order association entity IDs from a connection section.

    Second-order associations are stored as ``<!-- §assoc ENTITY_ID -->`` annotations
    in the connection section body of the source entity's .outgoing.md file.
    ``add_entities`` and ``remove_entities`` may both be specified in one call.
    """
    assert_engagement_write_root(repo_root)
    outgoing_path = _resolve_outgoing_path(registry, source_entity)

    if not outgoing_path.exists():
        raise ValueError(f"No outgoing file for '{source_entity}'")

    from .parse_existing import parse_outgoing_file

    parsed = parse_outgoing_file(outgoing_path)

    found = False
    for conn in parsed.connections:
        if _is_the_connection(conn, connection_type, target_entity):
            existing = as_optional_str_list(conn.get("associated_entities")) or []
            for eid in add_entities or []:
                if eid not in existing:
                    existing.append(eid)
            remove_set = set(remove_entities or [])
            existing = [e for e in existing if e not in remove_set]
            if existing:
                conn["associated_entities"] = existing
            else:
                conn.pop("associated_entities", None)
            found = True
            break

    if not found:
        raise ValueError(f"Connection '{connection_type} -> {target_entity}' not found in {outgoing_path.name}")

    content = format_outgoing_markdown(
        source_entity=source_entity,
        version=str(parsed.frontmatter.get("version", "0.1.0")),
        status=str(parsed.frontmatter.get("status", "draft")),
        last_updated=modification_stamp(),
        connections=parsed.connections,
    )
    conn_id = f"{connection_type} -> {target_entity}"

    if dry_run:
        return WriteResult(
            wrote=False,
            path=outgoing_path,
            artifact_id=conn_id,
            content=content,
            warnings=[],
            verification=None,
        )

    return _write_verify_clear(outgoing_path, content, verifier, conn_id, clear_repo_caches, repo_root)


def _write_verify_clear(
    outgoing_path: Path,
    content: str,
    verifier: ArtifactVerifier,
    conn_id: str,
    clear_repo_caches: Callable[[Path], None],
    repo_root: Path,
) -> WriteResult:
    """Write content, verify, rollback on failure, clear caches on success."""
    prev = outgoing_path.read_text(encoding="utf-8") if outgoing_path.exists() else None
    outgoing_path.parent.mkdir(parents=True, exist_ok=True)
    outgoing_path.write_text(content, encoding="utf-8")

    res = verifier.verify_outgoing_file(outgoing_path)
    vdict = verification_to_conn_dict(outgoing_path, res)

    if not res.valid:
        _rollback(outgoing_path, prev)
        return WriteResult(
            wrote=False,
            path=outgoing_path,
            artifact_id=conn_id,
            content=content,
            warnings=[],
            verification=vdict,
        )

    clear_repo_caches(outgoing_path)
    return WriteResult(
        wrote=True,
        path=outgoing_path,
        artifact_id=conn_id,
        content=None,
        warnings=[],
        verification=vdict,
    )
