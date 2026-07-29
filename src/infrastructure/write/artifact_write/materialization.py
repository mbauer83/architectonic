"""Materialization: diagram element → model entity/connection (SPEC-phase-3 §3).

Extends artifact_create_entity/artifact_add_connection with from_diagram_element
so the model write and binding update happen in one atomic operation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS
from src.domain.diagrams.bindings import Binding, BindingSubject, Target, bindings_to_raw


@dataclass(frozen=True)
class DiagramElementRef:
    """Identifies a diagram element to bind after creating a model artifact."""

    diagram_id: str
    diagram_element_id: str
    diagram_element_kind: str = "entity"  # "entity" | "connection"
    correspondence_kind_after: str = "represents"


@dataclass
class MaterializationResult:
    wrote: bool
    entity_id: str | None = None
    connection_id: str | None = None
    diagram_id: str = ""
    diagram_element_id: str = ""
    binding: dict[str, object] = field(default_factory=dict)
    proposed_entity_id: str | None = None
    proposed_connection_id: str | None = None
    proposed_binding: dict[str, object] = field(default_factory=dict)
    proposed_content: str | None = None
    verification: dict[str, object] | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------


def _dgr_path(repo_root: Path, diagram_id: str) -> Path:
    return repo_root / DIAGRAM_CATALOG / DIAGRAMS / f"{diagram_id}.puml"


def diagram_entity_exists(fm: dict[str, object], element_id: str) -> bool:
    """True if a diagram entity with element_id is declared in frontmatter."""
    raw = fm.get("diagram-entities")
    if not isinstance(raw, dict):
        return False
    for items in raw.values():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("id") == element_id:
                    return True
    return False


def diagram_connection_endpoints(
    fm: dict[str, object], conn_id: str
) -> tuple[str, str] | None:
    """Return (source_element_id, target_element_id) for a diagram connection, or None."""
    raw = fm.get("connections")
    if not isinstance(raw, list):
        return None
    for item in raw:
        if isinstance(item, dict) and item.get("id") == conn_id:
            src = str(item.get("source") or "")
            tgt = str(item.get("target") or "")
            return (src, tgt) if src and tgt else None
    return None


def find_represents_entity(bindings: list[Binding], element_id: str) -> str | None:
    """Return the model entity_id from the represents binding of the given diagram element."""
    for b in bindings:
        if (
            b.subject.kind == "entity"
            and b.subject.id == element_id
            and b.correspondence_kind == "represents"
            and b.target.entity_id is not None
        ):
            return b.target.entity_id
    return None


def filter_bindings(
    bindings: list[Binding],
    element_id: str,
    element_kind: str,
    kinds_to_remove: frozenset[str],
) -> list[Binding]:
    """Drop bindings for element_id where correspondence_kind is in kinds_to_remove."""
    return [
        b for b in bindings
        if not (
            b.subject.kind == element_kind
            and b.subject.id == element_id
            and b.correspondence_kind in kinds_to_remove
        )
    ]


# ---------------------------------------------------------------------------
# Entity materialization
# ---------------------------------------------------------------------------

_ENTITY_REPLACE_KINDS: frozenset[str] = frozenset({"refines", "abstracts"})


def materialize_entity(
    *,
    repo_root: Path,
    verifier: object,
    clear_repo_caches: Callable[[Path], None],
    ref: DiagramElementRef,
    artifact_type: str,
    name: str,
    summary: str | None = None,
    properties: dict[str, object] | None = None,
    attribute_types: dict[str, str] | None = None,
    notes: str | None = None,
    keywords: list[str] | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    dry_run: bool = True,
) -> MaterializationResult:
    """Create a model entity and atomically bind it to the diagram element.

    Dry-run: proposed_entity_id + proposed_binding, no file writes.
    Commit: creates entity then updates diagram bindings; on diagram failure the entity is rolled back.
    Replaces refines/abstracts bindings for the element; traces-to bindings are preserved.
    """
    from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.entity import create_entity  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    dgr_path = _dgr_path(repo_root, ref.diagram_id)
    if not dgr_path.exists():
        return MaterializationResult(wrote=False, error=f"Diagram '{ref.diagram_id}' not found")

    parsed = parse_diagram_file(dgr_path)
    if not diagram_entity_exists(parsed.frontmatter, ref.diagram_element_id):
        return MaterializationResult(
            wrote=False,
            error=f"Diagram entity '{ref.diagram_element_id}' not found in '{ref.diagram_id}'",
        )

    kept = filter_bindings(parsed.bindings, ref.diagram_element_id, "entity", _ENTITY_REPLACE_KINDS)

    # Dry-run entity creation to get the proposed artifact_id and content
    dr = create_entity(
        repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches,  # type: ignore[arg-type]
        artifact_type=artifact_type, name=name, summary=summary, properties=properties,
        attribute_types=attribute_types, notes=notes, keywords=keywords, artifact_id=None,
        version=version, status=status, last_updated=None, dry_run=True,
    )
    proposed_binding: dict[str, object] = {
        "subject": {"kind": "entity", "id": ref.diagram_element_id},
        "correspondence_kind": ref.correspondence_kind_after,
        "target": {"entity_id": dr.artifact_id},
    }

    if dry_run:
        return MaterializationResult(
            wrote=False, diagram_id=ref.diagram_id, diagram_element_id=ref.diagram_element_id,
            proposed_entity_id=dr.artifact_id, proposed_binding=proposed_binding,
            proposed_content=dr.content, verification=dr.verification,
        )

    if dr.verification and not dr.verification.get("valid", True):
        return MaterializationResult(wrote=False, error="Entity validation failed", verification=dr.verification)

    entity_result = create_entity(
        repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches,  # type: ignore[arg-type]
        artifact_type=artifact_type, name=name, summary=summary, properties=properties,
        attribute_types=attribute_types, notes=notes, keywords=keywords, artifact_id=None,
        version=version, status=status, last_updated=None, dry_run=False,
    )
    if not entity_result.wrote:
        return MaterializationResult(
            wrote=False, error="Entity creation failed", verification=entity_result.verification
        )

    new_b = Binding(
        id=f"bind-{ref.diagram_element_id}",
        subject=BindingSubject(kind="entity", id=ref.diagram_element_id),
        correspondence_kind=ref.correspondence_kind_after,
        target=Target(entity_id=entity_result.artifact_id),
    )
    final_raw = bindings_to_raw([b for b in kept if b.id != new_b.id] + [new_b])

    try:
        dgr_result = edit_diagram(
            repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches,  # type: ignore[arg-type]
            artifact_id=ref.diagram_id, bindings=final_raw, replace_bindings=True, dry_run=False,
        )
    except Exception as exc:
        entity_result.path.unlink(missing_ok=True)
        return MaterializationResult(wrote=False, error=f"Diagram update failed (entity rolled back): {exc}")

    if not dgr_result.wrote:
        entity_result.path.unlink(missing_ok=True)
        return MaterializationResult(
            wrote=False, error="Diagram binding update failed (entity rolled back)",
            verification=dgr_result.verification,
        )

    return MaterializationResult(
        wrote=True, entity_id=entity_result.artifact_id,
        diagram_id=ref.diagram_id, diagram_element_id=ref.diagram_element_id,
        binding={
            "subject": {"kind": "entity", "id": ref.diagram_element_id},
            "correspondence_kind": ref.correspondence_kind_after,
            "target": {"entity_id": entity_result.artifact_id},
        },
        warnings=list(entity_result.warnings or []),
    )


# ---------------------------------------------------------------------------
# Connection materialization
# ---------------------------------------------------------------------------

_CONN_REPLACE_KINDS: frozenset[str] = frozenset({"refines", "abstracts"})


def materialize_connection(
    *,
    repo_root: Path,
    registry: object,
    verifier: object,
    clear_repo_caches: Callable[[Path], None],
    ref: DiagramElementRef,
    connection_type: str,
    description: str | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    dry_run: bool = True,
) -> MaterializationResult:
    """Create a model connection from a diagram connection element atomically.

    Both endpoint diagram elements must have represents bindings to model entities.
    Dry-run: proposed_connection_id + binding, no file writes.
    Commit: adds connection then updates diagram bindings (abstracts/refines replaced).
    """
    from src.infrastructure.write.artifact_write.connection import add_connection  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    dgr_path = _dgr_path(repo_root, ref.diagram_id)
    if not dgr_path.exists():
        return MaterializationResult(wrote=False, error=f"Diagram '{ref.diagram_id}' not found")

    parsed = parse_diagram_file(dgr_path)
    endpoints = diagram_connection_endpoints(parsed.frontmatter, ref.diagram_element_id)
    if endpoints is None:
        return MaterializationResult(
            wrote=False,
            error=f"Diagram connection '{ref.diagram_element_id}' not found in '{ref.diagram_id}'",
        )
    src_elem, tgt_elem = endpoints

    src_entity = find_represents_entity(parsed.bindings, src_elem)
    tgt_entity = find_represents_entity(parsed.bindings, tgt_elem)
    if src_entity is None:
        return MaterializationResult(
            wrote=False, error=f"Source '{src_elem}' has no represents binding to a model entity",
        )
    if tgt_entity is None:
        return MaterializationResult(
            wrote=False, error=f"Target '{tgt_elem}' has no represents binding to a model entity",
        )

    proposed_conn_id = f"{src_entity}---{tgt_entity}@@{connection_type}"
    kept = filter_bindings(parsed.bindings, ref.diagram_element_id, "connection", _CONN_REPLACE_KINDS)
    proposed_binding: dict[str, object] = {
        "subject": {"kind": "connection", "id": ref.diagram_element_id},
        "correspondence_kind": "represents",
        "target": {"connection_id": proposed_conn_id},
    }

    if dry_run:
        return MaterializationResult(
            wrote=False, diagram_id=ref.diagram_id, diagram_element_id=ref.diagram_element_id,
            proposed_connection_id=proposed_conn_id, proposed_binding=proposed_binding,
        )

    conn_result = add_connection(
        repo_root=repo_root, registry=registry, verifier=verifier,  # type: ignore[arg-type]
        clear_repo_caches=clear_repo_caches, source_entity=src_entity,
        connection_type=connection_type, target_entity=tgt_entity,
        description=description, version=version, status=status, last_updated=None, dry_run=False,
    )
    if not conn_result.wrote:
        return MaterializationResult(
            wrote=False, error="Connection creation failed", verification=conn_result.verification,
        )

    new_b = Binding(
        id=f"bind-{ref.diagram_element_id}",
        subject=BindingSubject(kind="connection", id=ref.diagram_element_id),
        correspondence_kind="represents",
        target=Target(connection_id=conn_result.artifact_id),
    )
    final_raw = bindings_to_raw([b for b in kept if b.id != new_b.id] + [new_b])

    try:
        dgr_result = edit_diagram(
            repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches,  # type: ignore[arg-type]
            artifact_id=ref.diagram_id, bindings=final_raw, replace_bindings=True, dry_run=False,
        )
    except Exception as exc:
        return MaterializationResult(wrote=False, error=f"Diagram update failed after connection creation: {exc}")

    if not dgr_result.wrote:
        return MaterializationResult(
            wrote=False, error="Diagram binding update failed after connection creation",
            verification=dgr_result.verification,
        )

    return MaterializationResult(
        wrote=True, connection_id=conn_result.artifact_id,
        diagram_id=ref.diagram_id, diagram_element_id=ref.diagram_element_id,
        binding={
            "subject": {"kind": "connection", "id": ref.diagram_element_id},
            "correspondence_kind": "represents",
            "target": {"connection_id": conn_result.artifact_id},
        },
        warnings=list(conn_result.warnings or []),
    )
