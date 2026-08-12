from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path

from src.application.global_reference_endpoints import GLOBAL_REFERENCE_SOURCE_ERROR, effective_endpoint
from src.application.modeling.artifact_write import format_outgoing_markdown
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName
from src.domain.repository.connection_declaration import (
    ConnectionDeclaration,
    format_connection_declaration,
    parse_connection_declarations,
)
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.atomic_file import write_atomic

from .boundary import assert_engagement_write_root, modification_stamp, normalize_specializations
from .entity_frontmatter import entity_artifact_type
from .mediated_leg_guard import refuse_inadmissible_leg
from .types import WriteResult


@lru_cache(maxsize=None)
def _junction_types() -> frozenset[str]:
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415, process_runtime_catalogs

    return frozenset(get_module_registry().entity_types_with_class(ElementClassName("junction")))


def verification_to_conn_dict(path: Path, res) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "connection",
        "valid": res.valid,
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message, "location": i.location} for i in res.issues
        ],
    }


def _validate_inputs(
    registry: ArtifactRegistry,
    connection_type: str,
    source_entity: str,
    target_entity: str,
    extra_known_ids: frozenset[str] = frozenset(),
) -> None:
    from src.infrastructure.app_bootstrap import (  # noqa: PLC0415, process_runtime_catalogs
        build_runtime_catalogs,
        get_module_registry,
    )

    reg = get_module_registry()
    if reg.find_connection_type(ConnectionTypeName(connection_type)) is None:
        raise ValueError(f"Unknown connection type: {connection_type!r}")
    known_ids = registry.entity_ids() | extra_known_ids
    known_short_ids = {stable_id(k) for k in known_ids}
    if stable_id(source_entity) not in known_short_ids:
        raise ValueError(f"Source entity '{source_entity}' not found in model")
    if stable_id(target_entity) not in known_short_ids:
        raise ValueError(f"Target entity '{target_entity}' not found in model")

    source_endpoint = effective_endpoint(registry, source_entity)
    target_endpoint = effective_endpoint(registry, target_entity)
    catalogs = build_runtime_catalogs(reg)
    refuse_inadmissible_leg(registry, catalogs, connection_type, source_entity, target_entity)
    if source_endpoint.is_global_reference and not catalogs.connections.is_symmetric(connection_type):
        raise ValueError(GLOBAL_REFERENCE_SOURCE_ERROR)
    src_type = source_endpoint.entity_type
    tgt_type = target_endpoint.entity_type
    if src_type and tgt_type:
        # A GAR endpoint is judged as the type it references; the source-side invariant
        # above already excludes directed relationships FROM a global reference.
        allowed = catalogs.connections.permissible_connection_types(src_type, tgt_type)
        if connection_type not in allowed:
            alt_str = ", ".join(allowed) if allowed else "none"
            gar_note = " (resolved through the global reference)" if (
                source_endpoint.is_global_reference or target_endpoint.is_global_reference
            ) else ""
            raise ValueError(
                f"Relationship '{connection_type}' is not permitted from "
                f"'{src_type}' to '{tgt_type}'{gar_note}. "
                f"Permitted alternatives: {alt_str}."
            )


def _assert_pair_writable(
    repo_root: Path, connection_type: str,
    specializations: Sequence[str] | None = None,
) -> None:
    """Refuse a write onto a quarantined
    ``(connection-type, specialization)`` pair, exactly as the entity paths do. Kept at the
    write boundary both transports funnel through, so REST and MCP cannot diverge."""
    from src.application.profile_quarantine import assert_not_quarantined  # noqa: PLC0415

    applied = normalize_specializations(specializations)
    assert_not_quarantined(
        repo_root, "connection", connection_type, list(applied) or [""],
        catalogs=process_runtime_catalogs(),
    )


def _connection_metadata(
    metadata: dict[str, object] | None, specializations: Sequence[str] | None = None
) -> dict[str, object]:
    """One per-connection metadata block from the inputs that feed it. The applied set is
    authoritative for its own key — it selects which schema applies, so it is never something
    the schema-declared attributes can overwrite. A single specialization is written as a
    scalar (byte-identical to existing files), several as a list (§15.2)."""
    block: dict[str, object] = dict(metadata) if metadata else {}
    applied = normalize_specializations(specializations)
    if len(applied) == 1:
        block["specialization"] = applied[0]
    elif applied:
        block["specialization"] = list(applied)
    else:
        block.pop("specialization", None)
    return block


def _resolve_outgoing_path(
    registry: ArtifactRegistry,
    source_entity: str,
    *,
    dry_run: bool = False,
    extra_known_ids: frozenset[str] = frozenset(),
) -> Path:
    source_file = registry.find_file_by_id(source_entity)
    if source_file is not None:
        return source_file.with_suffix(".outgoing.md")
    if dry_run and source_entity in extra_known_ids:
        # Provisional entity: return a synthetic path for content preview
        repo_roots = registry.repo_roots
        if repo_roots:
            return repo_roots[0] / f"{source_entity}.outgoing.md"
    raise ValueError(f"Cannot locate file for source entity '{source_entity}'")


def _build_content(
    outgoing_path: Path,
    source_entity: str,
    connection_type: str,
    target_entity: str,
    description: str | None,
    version: str,
    status: str,
    last_updated: str,
    src_multiplicity: str | None = None,
    tgt_multiplicity: str | None = None,
    specializations: Sequence[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> str:
    applied = normalize_specializations(specializations)
    if outgoing_path.exists():
        existing = outgoing_path.read_text(encoding="utf-8")
        # Duplicate check ignores multiplicities — same (conn_type, target) pair is a duplicate. Asked
        # of `connection_declaration`, which owns the grammar: the two `startswith` markers here were a
        # hand-rolled way of saying "this type, with or without a source multiplicity", and the bracket
        # stripping below them was a third copy of the parser's own.
        for declaration in parse_connection_declarations(existing):
            same_pair = declaration.conn_type == connection_type and stable_id(
                declaration.target_id
            ) == stable_id(target_entity)
            if same_pair:
                raise ValueError(
                    f"Connection '{connection_type} → {target_entity}' already exists in {outgoing_path.name}"
                )
        # Appends the new section's formatted text without reparsing/redumping the rest of
        # the file — every other connection's byte content (incl. any uncommitted edit or
        # metadata block) is left untouched. Goes through the one shared grammar
        # component (format_connection_declaration) rather than hand-rolling the header/
        # metadata/description text, so this path and the "new file" path below can never
        # silently diverge in shape (e.g. one supporting the metadata block, the other not).
        decl = ConnectionDeclaration(
            conn_type=connection_type,
            target_id=target_entity,
            src_multiplicity=src_multiplicity or "",
            tgt_multiplicity=tgt_multiplicity or "",
            description=(description or "").strip(),
            metadata=_connection_metadata(metadata, applied),
        )
        return existing.rstrip("\n") + "\n\n" + format_connection_declaration(decl) + "\n"

    conn_dict: dict[str, object] = {
        "connection_type": connection_type,
        "target_entity": target_entity,
        "description": description or "",
    }
    if src_multiplicity:
        conn_dict["src_multiplicity"] = src_multiplicity
    if tgt_multiplicity:
        conn_dict["tgt_multiplicity"] = tgt_multiplicity
    if len(applied) == 1:
        conn_dict["specialization"] = applied[0]
    elif applied:
        conn_dict["specialization"] = list(applied)
    if metadata:
        conn_dict["metadata"] = dict(metadata)
    return format_outgoing_markdown(
        source_entity=source_entity,
        version=version,
        status=status,
        last_updated=last_updated,
        connections=[conn_dict],
    )


def _write_and_verify(
    outgoing_path: Path,
    content: str,
    verifier: ArtifactVerifier,
    source_entity: str,
    connection_type: str,
    target_entity: str,
) -> WriteResult:
    prev = outgoing_path.read_text(encoding="utf-8") if outgoing_path.exists() else None
    outgoing_path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(outgoing_path, content)

    res = verifier.verify_outgoing_file(outgoing_path)
    conn_id = f"{stable_id(source_entity)}---{stable_id(target_entity)}@@{connection_type}"

    if not res.valid:
        _rollback(outgoing_path, prev)
        return WriteResult(
            wrote=False,
            path=outgoing_path,
            artifact_id=conn_id,
            content=content,
            warnings=[],
            verification=verification_to_conn_dict(outgoing_path, res),
        )

    return WriteResult(
        wrote=True,
        path=outgoing_path,
        artifact_id=conn_id,
        content=None,
        warnings=[],
        verification=verification_to_conn_dict(outgoing_path, res),
    )


def _rollback(path: Path, prev: str | None) -> None:
    if prev is None:
        try:
            path.unlink()
        except OSError:
            pass
    else:
        write_atomic(path, prev)


def _canonical_entity_id(
    registry: ArtifactRegistry, entity_id: str, extra_known_ids: frozenset[str] = frozenset()
) -> str:
    """The full (PREFIX@epoch.random.slug) form of a possibly short-form id.

    Persisted outgoing files must always carry the full form: the read model joins a
    connection's endpoints to entity records by full id, so a short form written
    verbatim (e.g. as a fresh file's ``source-entity``) produces a connection that
    never joins — indexed but invisible to traversal and viewpoints."""
    short = stable_id(entity_id)
    for known in registry.entity_ids() | extra_known_ids:
        if stable_id(known) == short:
            return known
    return entity_id


def add_connection(
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
    src_multiplicity: str | None = None,
    tgt_multiplicity: str | None = None,
    specializations: Sequence[str] | None = None,
    metadata: dict[str, object] | None = None,
    extra_known_ids: frozenset[str] = frozenset(),
) -> WriteResult:
    """Add a connection to the source entity's .outgoing.md file.

    ``metadata`` carries the per-connection attributes declared by the connection type's
    effective metadata schema (base ⊕ specialization ⊕ bound profiles). ``specialization`` /
    ``specializations`` stay their own arguments because they select WHICH schema applies; a
    concept may carry several (§15.2).
    """
    assert_engagement_write_root(repo_root)
    _validate_inputs(registry, connection_type, source_entity, target_entity, extra_known_ids)
    _assert_pair_writable(repo_root, connection_type, specializations)
    source_entity = _canonical_entity_id(registry, source_entity, extra_known_ids)
    target_entity = _canonical_entity_id(registry, target_entity, extra_known_ids)

    if src_multiplicity or tgt_multiplicity:
        for eid, label in ((source_entity, "source"), (target_entity, "target")):
            if entity_artifact_type(registry, eid) in _junction_types():
                raise ValueError(
                    f"Multiplicities are not permitted at junction connection-ends "
                    f"(the {label} entity '{eid}' is a junction)."
                )

    last = last_updated or modification_stamp()
    outgoing_path = _resolve_outgoing_path(registry, source_entity, dry_run=dry_run, extra_known_ids=extra_known_ids)
    conn_id = f"{stable_id(source_entity)}---{stable_id(target_entity)}@@{connection_type}"

    content = _build_content(
        outgoing_path,
        source_entity,
        connection_type,
        target_entity,
        description,
        version,
        status,
        last,
        src_multiplicity=src_multiplicity,
        tgt_multiplicity=tgt_multiplicity,
        specializations=specializations,
        metadata=metadata,
    )

    if dry_run:
        return WriteResult(
            wrote=False,
            path=outgoing_path,
            artifact_id=conn_id,
            content=content,
            warnings=[],
            verification=None,
        )

    result = _write_and_verify(outgoing_path, content, verifier, source_entity, connection_type, target_entity)
    if result.wrote:
        clear_repo_caches(outgoing_path)
    return result
