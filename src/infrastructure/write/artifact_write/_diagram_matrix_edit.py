"""Matrix-diagram branch of ``diagram_edit.edit_diagram``.

Split out to keep ``diagram_edit.py`` (PUML-oriented) within the LoC policy —
matrix diagrams are markdown tables, not PUML, so their edit contract is
metadata + group move only, not the full field-merging logic of a PUML edit.
"""

from collections.abc import Callable
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier

from .types import WriteResult


def edit_matrix_diagram(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    diagram_path: Path,
    artifact_id: str,
    name: str | None,
    keywords: list[str] | None,
    version: str | None,
    status: str | None,
    tlp: str | None,
    group: str | None,
    dry_run: bool,
    puml: str | None,
    diagram_entities: dict[str, object] | None,
    diagram_connections: list[dict[str, object]] | None,
    entity_ids_used: list[str] | None,
    connection_ids_used: list[str] | None,
    view_derivations: list[dict[str, object]] | None,
    bindings: list[dict[str, object]] | None,
    replace_bindings: bool,
    edge_labels_given: bool,
    viewpoint: dict[str, object] | None = None,
) -> WriteResult:
    """Matrix-diagram branch of ``edit_diagram``: metadata + group move only.

    Matrix diagrams are markdown tables, not PUML — the fields below only make
    sense for PUML-bodied diagrams, so they are rejected here rather than
    silently mishandled. Content edits go through ``create_matrix`` (upsert,
    exposed as the ``artifact_create_matrix`` MCP tool) instead.
    """
    unsupported = [
        pname for pname, pval in (
            ("puml", puml), ("diagram_entities", diagram_entities),
            ("diagram_connections", diagram_connections),
            ("entity_ids_used", entity_ids_used), ("connection_ids_used", connection_ids_used),
            ("view_derivations", view_derivations), ("bindings", bindings),
            ("viewpoint", viewpoint),
        ) if pval is not None
    ]
    if replace_bindings:
        unsupported.append("replace_bindings")
    if edge_labels_given:
        unsupported.append("edge_labels")
    if unsupported:
        raise ValueError(
            f"Matrix diagrams do not support {', '.join(unsupported)} via artifact_edit_diagram; "
            "call artifact_create_matrix with artifact_id set to change table content."
        )
    if verifier.registry is None:
        raise ValueError("Registry required to edit matrix diagrams")

    from .matrix import edit_matrix_metadata  # noqa: PLC0415

    return edit_matrix_metadata(
        repo_root=repo_root,
        registry=verifier.registry,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        diagram_path=diagram_path,
        artifact_id=artifact_id,
        name=name,
        keywords=keywords,
        version=version,
        status=status,
        tlp=tlp,
        group=group,
        dry_run=dry_run,
    )
