"""Binding-mode handlers for artifact_edit_diagram.

Supported modes:
  refresh-derivation  — run the view_derivations strategy, return diff + base_revision (no write)
  apply-diff          — apply a diff returned by refresh-derivation (stale-write check)
  propose-bindings    — return base_revision + binding proposals for given model ids (no write)
  detach-binding      — remove a single binding by id (write)
"""

from __future__ import annotations

from pathlib import Path

from src.application.repo_path_helpers import diagram_source_root, resolve_diagram_source_path
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.write._common import _out
from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file


def _diagram_path(root: Path, artifact_id: str, key: str) -> Path:
    """Resolve a diagram's source path group-aware, so binding modes work on diagrams in a
    group collection (or other subdirectory), not only a flat layout."""
    from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

    index = shared_artifact_index([Path(p) for p in key.split("|") if p])
    resolved = resolve_diagram_source_path(root, artifact_id, index.find_file_by_id)
    return resolved if resolved is not None else diagram_source_root(root) / f"{artifact_id}.puml"


def _require_exists(path: Path, artifact_id: str) -> None:
    if not path.exists():
        raise ValueError(f"Diagram '{artifact_id}' not found at {path}")


def _stale_conflict(current_revision: str) -> dict[str, object]:
    return {
        "conflict": True,
        "message": "Diagram changed since diff was computed; re-run refresh-derivation.",
        "current_revision": current_revision,
    }


def dispatch_binding_mode(
    *,
    mode: str,
    artifact_id: str,
    root: Path,
    key: str,
    derivation_id: str | None,
    diff: dict[str, object] | None,
    base_revision: str | None,
    entity_ids: list[str] | None,
    connection_ids_param: list[str] | None,
    binding_id: str | None,
    dry_run: bool,
) -> dict[str, object]:
    path = _diagram_path(root, artifact_id, key)

    if mode == "refresh-derivation":
        return _refresh_derivation(artifact_id, derivation_id, path, key)
    if mode == "apply-diff":
        return _apply_diff(artifact_id, diff, base_revision, path, root, key, dry_run)
    if mode == "propose-bindings":
        return _propose_bindings(artifact_id, entity_ids, connection_ids_param, path, key)
    if mode == "detach-binding":
        return _detach_binding(artifact_id, binding_id, path, root, key, dry_run)
    raise ValueError(
        f"Unknown mode '{mode}'. "
        "Expected: refresh-derivation, apply-diff, propose-bindings, detach-binding"
    )


# ---------------------------------------------------------------------------
# refresh-derivation (read-only)
# ---------------------------------------------------------------------------


def _refresh_derivation(
    artifact_id: str,
    derivation_id: str | None,
    path: Path,
    key: str,
) -> dict[str, object]:
    if not derivation_id:
        raise ValueError("refresh-derivation requires derivation_id")
    _require_exists(path, artifact_id)

    parsed = parse_diagram_file(path)
    vd_entry = next((vd for vd in parsed.view_derivations if vd.id == derivation_id), None)
    if vd_entry is None:
        raise ValueError(f"Derivation '{derivation_id}' not found in diagram '{artifact_id}'")

    from src.application.derivation.refresh import compute_derivation_diff  # noqa: PLC0415
    from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

    roots = [Path(p) for p in key.split("|") if p]
    index = shared_artifact_index(roots)
    catalogs = process_runtime_catalogs()
    diff = compute_derivation_diff(
        path, parsed.frontmatter, vd_entry, index, catalogs.derivation, ontology_catalog=catalogs.module_catalog,
    )
    return diff.to_dict()


# ---------------------------------------------------------------------------
# apply-diff (write)
# ---------------------------------------------------------------------------


def _apply_diff(
    artifact_id: str,
    diff_dict: dict[str, object] | None,
    client_base_revision: str | None,
    path: Path,
    root: Path,
    key: str,
    dry_run: bool,
) -> dict[str, object]:
    if not diff_dict or not client_base_revision:
        raise ValueError("apply-diff requires diff and base_revision")
    _require_exists(path, artifact_id)

    from src.application.derivation.refresh import (  # noqa: PLC0415
        SelectionDelta,
        apply_selection_delta,
        compute_revision,
    )
    from src.infrastructure.mcp.artifact_mcp.context import authoritative_callbacks_for, verifier_for  # noqa: PLC0415

    current_revision = compute_revision(path)
    if current_revision != client_base_revision:
        return _stale_conflict(current_revision)

    parsed = parse_diagram_file(path)
    fm = parsed.frontmatter
    derivation_id = str(diff_dict.get("derivation_id") or "")

    raw_delta = diff_dict.get("selection_delta")
    raw_delta = raw_delta if isinstance(raw_delta, dict) else {}
    delta = SelectionDelta(
        add_included_entity_ids=list(raw_delta.get("add_included_entity_ids") or []),
        add_excluded_entity_ids=list(raw_delta.get("add_excluded_entity_ids") or []),
        add_included_connection_ids=list(raw_delta.get("add_included_connection_ids") or []),
        add_excluded_connection_ids=list(raw_delta.get("add_excluded_connection_ids") or []),
        remove_included_entity_ids=list(raw_delta.get("remove_included_entity_ids") or []),
        remove_included_connection_ids=list(raw_delta.get("remove_included_connection_ids") or []),
    )

    vds_raw = fm.get("view_derivations")
    raw_vds = [v for v in vds_raw if isinstance(v, dict)] if isinstance(vds_raw, list) else []
    updated_vds = apply_selection_delta(raw_vds, derivation_id, delta) if derivation_id else raw_vds

    rids_raw = diff_dict.get("remove_binding_ids")
    remove_set = set(rids_raw) if isinstance(rids_raw, list) else set()
    bindings_raw = fm.get("bindings")
    raw_bindings = [b for b in bindings_raw if isinstance(b, dict)] if isinstance(bindings_raw, list) else []
    updated_bindings = [b for b in raw_bindings if str(b.get("id") or "") not in remove_set]

    verifier = verifier_for(key, include_registry=True)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(root)

    result = edit_diagram(
        repo_root=root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        view_derivations=updated_vds or None,
        bindings=updated_bindings,
        replace_bindings=True,
        dry_run=dry_run,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


# ---------------------------------------------------------------------------
# propose-bindings (read-only)
# ---------------------------------------------------------------------------


def _propose_bindings(
    artifact_id: str,
    entity_ids: list[str] | None,
    connection_ids_param: list[str] | None,
    path: Path,
    key: str,
) -> dict[str, object]:
    _require_exists(path, artifact_id)

    from src.application.derivation.binding_proposals import (  # noqa: PLC0415
        build_connection_proposals,
        build_entity_proposals,
    )
    from src.application.derivation.refresh import compute_revision  # noqa: PLC0415
    from src.domain.diagrams.allowed_bindings import AllowedBindingsSpec  # noqa: PLC0415
    from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

    base_revision = compute_revision(path)
    parsed = parse_diagram_file(path)
    diagram_type_name = str(parsed.frontmatter.get("diagram-type", ""))

    allowed_bindings: AllowedBindingsSpec | None = None
    if diagram_type_name:
        mod = process_runtime_catalogs().diagram_types.find_diagram_type(diagram_type_name)
        if mod is not None:
            guidance = mod.write_guidance()
            allowed_bindings = guidance.allowed_bindings

    roots = [Path(p) for p in key.split("|") if p]
    index = shared_artifact_index(roots)

    if allowed_bindings is not None and not allowed_bindings.is_empty():
        entity_proposals = build_entity_proposals(entity_ids or [], allowed_bindings, index)
        connection_proposals = build_connection_proposals(connection_ids_param or [], allowed_bindings, index)
    else:
        entity_proposals = [{"model_entity_id": eid} for eid in (entity_ids or [])]
        connection_proposals = [{"model_connection_id": cid} for cid in (connection_ids_param or [])]

    result: dict[str, object] = {
        "base_revision": base_revision,
        "entity_proposals": entity_proposals,
        "connection_proposals": connection_proposals,
    }
    if diagram_type_name:
        result["diagram_type"] = diagram_type_name
    return result


# ---------------------------------------------------------------------------
# detach-binding (write)
# ---------------------------------------------------------------------------


def _detach_binding(
    artifact_id: str,
    binding_id: str | None,
    path: Path,
    root: Path,
    key: str,
    dry_run: bool,
) -> dict[str, object]:
    if not binding_id:
        raise ValueError("detach-binding requires binding_id")
    _require_exists(path, artifact_id)

    from src.infrastructure.mcp.artifact_mcp.context import authoritative_callbacks_for, verifier_for  # noqa: PLC0415

    parsed = parse_diagram_file(path)
    fm = parsed.frontmatter
    bindings_raw = fm.get("bindings")
    raw_bindings = [b for b in bindings_raw if isinstance(b, dict)] if isinstance(bindings_raw, list) else []
    remaining = [b for b in raw_bindings if str(b.get("id") or "") != binding_id]

    if len(remaining) == len(raw_bindings):
        return {"detached": False, "message": f"Binding '{binding_id}' not found in '{artifact_id}'"}

    verifier = verifier_for(key, include_registry=True)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(root)

    result = edit_diagram(
        repo_root=root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        bindings=remaining,
        replace_bindings=True,
        dry_run=dry_run,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    out = _out(result, dry_run=dry_run)
    out["detached"] = True
    out["detached_binding_id"] = binding_id
    return out
