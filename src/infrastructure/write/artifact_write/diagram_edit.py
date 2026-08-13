"""Diagram editing operations."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.application.candidate_repository import CandidateRepository
from src.application.modeling.artifact_write import format_diagram_puml
from src.application.modeling.artifact_write_layout import ensure_puml_layout, rebuild_puml_layout
from src.application.repo_path_helpers import diagram_source_root, resolve_diagram_source_path
from src.application.verification.artifact_verifier import ArtifactVerifier

from ._diagram_group_move import _verification_to_dict, commit_diagram_write
from .boundary import assert_engagement_write_root, modification_stamp
from .coerce import as_optional_str_list
from .diagram_references import (
    _collect_diagram_renderer_references,
    _infer_reference_ids_from_puml,
    _merge_reference_ids,
    _prepare_diagram_puml_body,
    _prune_unknown_references,
    _restate_generated_declarations,
    diagram_entities_are_authoritative,
)
from .diagram_render import _render_diagram_entities_puml
from .parse_existing import parse_diagram_file
from .types import WriteResult


def _extract_workspace_ids(fm: dict, module: object) -> set[str]:
    """Return the set of workspace entity ids currently in the committed diagram frontmatter."""
    result: set[str] = set()
    try:
        de: dict[str, Any] = fm.get("diagram-entities") or {}
        for ui_cfg in module.ui_config.diagram_only_types:  # type: ignore[attr-defined]
            if ui_cfg.identity_scope != "workspace":
                continue
            items: list[Any] = de.get(str(ui_cfg.entity_type)) or []
            for item in items:
                if isinstance(item, dict):
                    eid = str(item.get("id") or "")
                    if eid:
                        result.add(eid)
    except Exception:  # noqa: BLE001
        pass
    return result


_EDGE_LABELS_UNSET = object()
_VIEWPOINT_UNSET = object()


def edit_diagram(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    puml: str | None = None,
    name: str | None = None,
    keywords: list[str] | None = ...,  # type: ignore[assignment]
    diagram_entities: dict[str, object] | None = None,
    diagram_connections: list[dict[str, object]] | None = None,
    entity_ids_used: list[str] | None = None,
    connection_ids_used: list[str] | None = None,
    view_derivations: list[dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
    replace_bindings: bool = False,
    version: str | None = None,
    status: str | None = None,
    tlp: str | None = None,
    viewpoint: dict[str, object] | None = _VIEWPOINT_UNSET,  # type: ignore[assignment]
    edge_labels: dict[str, str | None] | None = _EDGE_LABELS_UNSET,  # type: ignore[assignment]
    group: str | None = None,
    rebuild_layout: bool = False,
    dry_run: bool,
    committed_repo: CandidateRepository | None = None,
    authored_groupings: list[dict[str, object]] | None = None,
    manual_layout: bool | None = None,
) -> WriteResult:
    """Edit an existing diagram file.

    If ``puml`` is provided, replaces the PUML body and re-runs auto-layout.
    Other fields (name, keywords, version, status) update frontmatter only.
    ``group`` re-homes the diagram to a different diagram-collection slug
    (moving the source file and its rendered outputs); omit to leave it in
    place. Always re-verifies and re-renders PNG on successful write.

    ``viewpoint``: the ``ViewpointApplication`` frontmatter mapping (``{slug, version,
    enforcement_override?, derivation_params?}``) — omit to keep the diagram's existing
    application (if any) unchanged; pass a mapping to replace it; pass ``None`` explicitly
    to clear it (e.g. a GUI viewpoint selector set back to "none"). Validated and normalized
    through the same parse/serialize grammar the verifier reads back.

    Matrix diagrams (``diagram-type: matrix``) are markdown tables, not PUML:
    only name/keywords/version/status/tlp/group are supported (metadata + group
    move, table content preserved); ``puml``/``diagram_entities``/``viewpoint``/etc. raise
    ``ValueError`` — use ``create_matrix`` (the ``artifact_create_matrix`` MCP
    tool) with ``artifact_id`` set instead.
    """
    from src.application.modeling.binding_normalize import normalize_bindings, strip_diagram_shorthand
    from src.domain.diagrams.bindings import bindings_to_raw

    assert_engagement_write_root(repo_root)
    warnings: list[str] = []

    _find = verifier.registry.find_file_by_id if verifier.registry is not None else None
    diagram_path = resolve_diagram_source_path(repo_root, artifact_id, _find)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found under {diagram_source_root(repo_root)}")

    parsed = parse_diagram_file(diagram_path)
    fm = parsed.frontmatter
    # A caller-supplied short/stale-slug id resolved to diagram_path above; canonicalize to
    # the file's own recorded id now so nothing downstream (frontmatter, group-move filename,
    # WriteResult) writes the short form back out as if it were the real artifact id.
    artifact_id = str(fm.get("artifact-id", artifact_id))

    eff_name = name if name is not None else str(fm.get("name", ""))
    eff_version = version if version is not None else str(fm.get("version", "0.1.0"))
    eff_status = status if status is not None else str(fm.get("status", "draft"))
    _fm_tlp = fm.get("tlp")
    eff_tlp = tlp if tlp is not None else (str(_fm_tlp) if isinstance(_fm_tlp, str) else None)
    eff_keywords = keywords if keywords is not ... else as_optional_str_list(fm.get("keywords"))
    eff_diagram_entities = diagram_entities if diagram_entities is not None else fm.get("diagram-entities")
    eff_diagram_connections = diagram_connections if diagram_connections is not None else fm.get("connections")
    diagram_type = str(fm.get("diagram-type", "archimate"))

    if diagram_type == "matrix":
        from ._diagram_matrix_edit import edit_matrix_diagram  # noqa: PLC0415

        return edit_matrix_diagram(
            repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches,
            diagram_path=diagram_path, artifact_id=artifact_id, name=name,
            keywords=None if keywords is ... else keywords,
            version=version, status=status, tlp=tlp, group=group, dry_run=dry_run,
            puml=puml, diagram_entities=diagram_entities, diagram_connections=diagram_connections,
            entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
            view_derivations=view_derivations, bindings=bindings, replace_bindings=replace_bindings,
            edge_labels_given=edge_labels is not _EDGE_LABELS_UNSET,
            viewpoint=None if viewpoint is _VIEWPOINT_UNSET else viewpoint,
        )

    raw_format_version = fm.get("diagram-format-version")
    eff_format_version = (
        2 if diagram_type == "datatype"
        else raw_format_version if isinstance(raw_format_version, int)
        else None
    )
    if diagram_entities is not None:
        from src.application.identifier_allocator import get_default_allocator  # noqa: PLC0415
        from src.infrastructure.write.artifact_write.diagram_entity_identity import (  # noqa: PLC0415
            normalize_diagram_entity_identities,
        )
        diagram_entities, diagram_connections, bindings = normalize_diagram_entity_identities(  # type: ignore[assignment]
            diagram_type,
            diagram_entities,  # type: ignore[arg-type]
            list(diagram_connections or []),
            list(bindings or []),
            module_catalog=verifier._runtime_catalogs.diagram_types,
            allocator=get_default_allocator(),
        )
    eff_manual_layout = manual_layout if manual_layout is not None else fm.get("manual-layout") is True
    _raw_ag = fm.get("authored-groupings")
    _existing_ag = [g for g in _raw_ag if isinstance(g, dict)] if isinstance(_raw_ag, list) else []
    eff_authored_groupings = authored_groupings if authored_groupings is not None else _existing_ag
    eff_entity_ids_used = (
        entity_ids_used if entity_ids_used is not None else as_optional_str_list(fm.get("entity-ids-used"))
    )
    eff_connection_ids_used = (
        connection_ids_used if connection_ids_used is not None else as_optional_str_list(fm.get("connection-ids-used"))
    )

    # view_derivations: caller replaces; keep existing from file if caller omits
    _raw_vd = fm.get("view_derivations")
    existing_vd = [v for v in _raw_vd if isinstance(v, dict)] if isinstance(_raw_vd, list) else []
    eff_view_derivations: list[dict[str, object]] | None = (
        view_derivations if view_derivations is not None else (existing_vd or None)
    )

    # Bindings: existing from file + new from caller, then normalize shorthand from entities
    _raw_b = fm.get("bindings")
    existing_raw_bindings = [b for b in _raw_b if isinstance(b, dict)] if isinstance(_raw_b, list) else []
    merged_raw_bindings = list(bindings or []) if replace_bindings else existing_raw_bindings + list(bindings or [])
    norm_bindings = normalize_bindings(
        eff_diagram_entities if isinstance(eff_diagram_entities, dict) else None,
        merged_raw_bindings,
    )
    clean_entities = strip_diagram_shorthand(
        eff_diagram_entities if isinstance(eff_diagram_entities, dict) else None
    )

    # Workspace-id format check: validate any NEW workspace entity ids in this edit.
    if diagram_entities is not None and isinstance(clean_entities, dict):
        from src.application.verification._workspace_identity_rules import (
            validate_workspace_entity_ids,  # noqa: PLC0415
        )
        try:
            _dt_module = verifier._runtime_catalogs.diagram_types.find_diagram_type(diagram_type)
        except Exception:  # noqa: BLE001
            _dt_module = None
        if _dt_module is not None:
            _committed_ids = _extract_workspace_ids(fm, _dt_module)
            _ws_errors = validate_workspace_entity_ids(clean_entities, _dt_module, committed_ids=_committed_ids)
            from src.config.settings import datatype_type_references_blocking  # noqa: PLC0415
            if _ws_errors and datatype_type_references_blocking():
                return WriteResult(
                    wrote=False,
                    path=diagram_path,
                    artifact_id=artifact_id,
                    content=None,
                    warnings=warnings,
                    verification={
                        "path": str(diagram_path),
                        "file_type": "diagram",
                        "valid": False,
                        "issues": [
                            {"severity": "error", "code": "E335-fmt", "message": m, "location": str(diagram_path)}
                            for m in _ws_errors
                        ],
                    },
                )

    # E334 reference-impact: detect removed classifiers still referenced by other diagrams.
    if committed_repo is not None and diagram_entities is not None and isinstance(clean_entities, dict):
        from src.application.candidate_repository import candidate_with  # noqa: PLC0415
        from src.application.verification._verifier_contribution_runner import (  # noqa: PLC0415
            run_repository_contributions,
            workspace_types_from_catalogs,
        )
        from src.domain.ontology_representation.artifact_types import DiagramRecord  # noqa: PLC0415
        _new_diag = DiagramRecord(
            artifact_id=artifact_id, artifact_type="diagram",
            name=eff_name, version=eff_version, status=eff_status,
            diagram_type=diagram_type, path=diagram_path,
            extra={"diagram-entities": clean_entities},
        )
        _catalogs = getattr(verifier, "_catalogs", None)
        _ws = workspace_types_from_catalogs(_catalogs) if _catalogs is not None else {}
        _cand = candidate_with(committed_repo, changed_diagrams=[_new_diag], workspace_types=_ws)
        _rr = run_repository_contributions(
            candidate=_cand, committed=committed_repo, runtime_catalogs=_catalogs, repo_path=repo_root,
        )
        if _rr is not None and not _rr.valid:
            return WriteResult(
                wrote=False, path=diagram_path, artifact_id=artifact_id,
                content=None, warnings=warnings,
                verification=_verification_to_dict(diagram_path, _rr),
            )

    norm_bindings_raw = bindings_to_raw(norm_bindings)

    # Edge-label overrides: merge caller-supplied delta into existing map.
    # A None value for a key removes that key (single-key clear without full replacement).
    _raw_el = fm.get("edge-labels")
    existing_edge_labels: dict[str, str] = dict(_raw_el) if isinstance(_raw_el, dict) else {}
    if edge_labels is _EDGE_LABELS_UNSET:
        eff_edge_labels: dict[str, str] | None = existing_edge_labels or None
    else:
        merged: dict[str, str] = dict(existing_edge_labels)
        for k, v in (edge_labels or {}).items():
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v
        eff_edge_labels = merged or None

    # Determine PUML body; inject _scope_entity_id from scoped-by binding so the
    # C4 renderer uses model-backed mode for diagrams that previously used _scope_entity_id.
    if (
        eff_diagram_entities is not None
        and isinstance(eff_diagram_entities, dict)
        and puml is None
        and diagram_entities_are_authoritative(verifier, diagram_type)
    ):
        scope_eid = next(
            (b.target.entity_id for b in norm_bindings
             if b.correspondence_kind == "scoped-by" and b.subject.kind == "diagram"
             and b.target.entity_id),
            None,
        )
        render_entities: dict[str, object] = dict(eff_diagram_entities)
        if scope_eid and "_scope_entity_id" not in render_entities:
            render_entities["_scope_entity_id"] = scope_eid
        eff_diagram_conns = eff_diagram_connections if isinstance(eff_diagram_connections, list) else None
        puml_body = _render_diagram_entities_puml(
            diagram_type,
            eff_name,
            render_entities,
            eff_diagram_conns,
            repo_root,
            edge_labels=eff_edge_labels,
        )
        collected_entity_ids, collected_connection_ids = _collect_diagram_renderer_references(
            diagram_type,
            repo_root,
            render_entities,
            eff_diagram_conns,
            bindings=norm_bindings_raw,
        )
        eff_entity_ids_used = _merge_reference_ids(eff_entity_ids_used, collected_entity_ids)
        eff_connection_ids_used = _merge_reference_ids(eff_connection_ids_used, collected_connection_ids)
    elif puml is not None:
        # Untrusted input: reject file/network preprocessor directives before the body is
        # prepared, rendered (verification renders it), or stored — a submitted
        # `!include /etc/passwd` would otherwise exfiltrate a server file into the SVG.
        from src.infrastructure.rendering.puml_safety import assert_user_puml_safe  # noqa: PLC0415

        assert_user_puml_safe(puml)
        puml_body = puml.strip("\n") + "\n"
        puml_body = _prepare_diagram_puml_body(puml_body, repo_root, diagram_type)
        # Both are idempotent and both skip when [hidden] links are already present, so
        # user-provided explicit hidden chains are preserved either way.
        puml_body = rebuild_puml_layout(puml_body) if rebuild_layout else ensure_puml_layout(puml_body)
        inferred_entity_ids, inferred_connection_ids = _infer_reference_ids_from_puml(repo_root, puml_body)
        eff_entity_ids_used = _merge_reference_ids(eff_entity_ids_used, inferred_entity_ids)
        eff_connection_ids_used = _merge_reference_ids(eff_connection_ids_used, inferred_connection_ids)
    else:
        # No body supplied. A sync asked for the picture to be rebuilt, so its generated
        # ranking is recomputed; every other edit — a rename, a binding, a status change —
        # leaves the stored body exactly as the author last left it.
        puml_body = rebuild_puml_layout(parsed.puml_body) if rebuild_layout else parsed.puml_body
        # Except the generated declarations it inlines, which the author never wrote: a palette or
        # a line style is the ontology's, and a body that keeps its own copy had no way of hearing
        # about a change to one. The only route by which a manual-layout diagram hears at all.
        puml_body = _restate_generated_declarations(puml_body, repo_root, diagram_type)

    # Drop references to entities/connections that no longer exist (e.g. after a rename or
    # delete) so a stale cached reference cannot leave the diagram permanently unwritable.
    eff_entity_ids_used, eff_connection_ids_used = _prune_unknown_references(
        verifier.registry, eff_entity_ids_used, eff_connection_ids_used
    )

    from src.domain.viewpoints.viewpoint_application_parsing import normalize_viewpoint_frontmatter

    eff_viewpoint_raw = fm.get("viewpoint") if viewpoint is _VIEWPOINT_UNSET else viewpoint
    eff_viewpoint = normalize_viewpoint_frontmatter(eff_viewpoint_raw, target_kind="diagram", target_id=artifact_id)
    if viewpoint is not _VIEWPOINT_UNSET:
        # New applications only — an already-persisted value is a verifier concern.
        from src.infrastructure.write.artifact_write.diagram import (  # noqa: PLC0415
            _refuse_signal_viewpoint_persistence,
        )

        _refuse_signal_viewpoint_persistence(eff_viewpoint, verifier)

    content = format_diagram_puml(
        artifact_id=artifact_id,
        diagram_type=diagram_type,
        name=eff_name,
        version=eff_version,
        status=eff_status,
        last_updated=modification_stamp(),
        keywords=eff_keywords,
        diagram_entities=clean_entities,
        diagram_connections=eff_diagram_connections if isinstance(eff_diagram_connections, list) else None,
        entity_ids_used=eff_entity_ids_used,
        connection_ids_used=eff_connection_ids_used,
        view_derivations=eff_view_derivations,
        bindings=bindings_to_raw(norm_bindings) if norm_bindings else None,
        edge_labels=eff_edge_labels or None,
        puml_body=puml_body,
        tlp=eff_tlp,
        viewpoint=eff_viewpoint,
        diagram_format_version=eff_format_version,
        authored_groupings=eff_authored_groupings or None,
        manual_layout=eff_manual_layout,
    )

    return commit_diagram_write(
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        diagram_path=diagram_path,
        diagram_type=diagram_type,
        tlp=eff_tlp,
        group=group,
        content=content,
        warnings=warnings,
        dry_run=dry_run,
    )
