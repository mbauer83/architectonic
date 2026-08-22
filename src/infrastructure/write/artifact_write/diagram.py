import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.application.modeling.artifact_write import (
    DiagramConnectionInferenceMode,
    format_diagram_puml,
    generate_diagram_id,
)
from src.application.modeling.artifact_write_layout import ensure_puml_layout
from src.application.repo_path_helpers import diagram_source_confidential_root, diagram_source_root
from src.application.verification._issue_serialization import as_issue_dict
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_types import ENTITY_ID_RE, Issue, Severity
from src.domain.diagrams.bindings import Binding
from src.domain.repository.groups import UNCATEGORIZED

from ._artifact_deduplication import extract_friendly_slug, get_repository, validate_diagram_unique
from .boundary import assert_engagement_write_root
from .diagram_confidentiality import ensure_confidential_gitignore, is_confidential_diagram_source
from .diagram_references import (
    _collect_diagram_renderer_references,
    _infer_reference_ids_from_puml,
    _merge_reference_ids,
    _prepare_diagram_puml_body,
)
from .diagram_render import (
    _render_diagram_entities_puml,
    render_diagram_outputs,
)
from .diagram_render_input import render_entities_restored
from .types import WriteResult
from .verify import verify_content_in_temp_path


def _verification_to_dict(path: Path, res) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "diagram",
        "valid": res.valid,
        "issues": [as_issue_dict(i) for i in res.issues],
    }


@dataclass(frozen=True)
class _DiagramBuild:
    """Outcome of resolving a diagram's body, id, and reference sets before formatting."""

    puml_body: str
    effective_id: str
    entity_ids_used: list[str] | None
    connection_ids_used: list[str] | None


def _build_model_backed(
    *,
    diagram_type: str,
    name: str,
    repo_root: Path,
    diagram_entities: dict[str, object],
    diagram_connections: list[dict[str, object]] | None,
    norm_bindings: list[Binding],
    norm_bindings_raw: list[dict[str, object]] | None,
    effective_id: str | None,
    entity_ids_used: list[str] | None,
    connection_ids_used: list[str] | None,
    view_derivations: list[dict[str, object]] | None,
) -> _DiagramBuild:
    """Render a diagram from structured entities/connections, collecting referenced ids."""
    render_entities = render_entities_restored(dict(diagram_entities), norm_bindings, view_derivations)
    puml_body = _render_diagram_entities_puml(diagram_type, name, render_entities, diagram_connections, repo_root)
    collected_e, collected_c = _collect_diagram_renderer_references(
        diagram_type, repo_root, render_entities, diagram_connections, bindings=norm_bindings_raw
    )
    return _DiagramBuild(
        puml_body=puml_body,
        effective_id=effective_id or generate_diagram_id(diagram_type, name),
        entity_ids_used=_merge_reference_ids(entity_ids_used, collected_e),
        connection_ids_used=_merge_reference_ids(connection_ids_used, collected_c),
    )


def _build_from_puml(
    *,
    diagram_type: str,
    name: str,
    repo_root: Path,
    puml: str,
    effective_id: str | None,
    auto_include_stereotypes: bool,
    entity_ids_used: list[str] | None,
    connection_ids_used: list[str] | None,
) -> _DiagramBuild:
    """Prepare a hand-authored PUML body, inferring its referenced ids and minting an id if needed."""
    eid = effective_id
    if eid is None:
        # Only adopt the @startuml token as the artifact-id when it is itself a canonical id
        # (round-tripping a generated diagram); a bare label must not leak into the id (→ W041).
        m = re.search(r"@startuml\s+(\S+)", puml)
        if m and ENTITY_ID_RE.match(m.group(1).strip()):
            eid = m.group(1).strip()
    eid = eid or generate_diagram_id(diagram_type, name)

    puml_body = puml.strip("\n") + "\n"
    if auto_include_stereotypes:
        puml_body = _prepare_diagram_puml_body(puml_body, repo_root, diagram_type)
    puml_body = ensure_puml_layout(puml_body)
    # A fresh artifact has no stored value to carry, so merging the caller's own argument with what
    # the body draws is right here and the reconcile is not needed. What inference could not decide
    # is likewise nothing to salvage.
    inferred_e, inferred_c, _undecided = _infer_reference_ids_from_puml(repo_root, puml_body)
    return _DiagramBuild(
        puml_body=puml_body,
        effective_id=eid,
        entity_ids_used=_merge_reference_ids(entity_ids_used, inferred_e),
        connection_ids_used=_merge_reference_ids(connection_ids_used, inferred_c),
    )


def _refuse_signal_viewpoint_persistence(viewpoint_fm: dict | None, verifier: ArtifactVerifier) -> None:
    """Signal-styled output is classification-bearing and ephemeral: a viewpoint
    that DECLARES a security-signal source may never be applied to a
    git-persisted diagram (refusal is semantic, not value-dependent). The
    stamped export endpoint is the sanctioned way to take styled output out."""
    if not viewpoint_fm:
        return
    slug = str(viewpoint_fm.get("slug") or "")
    if not slug:
        return
    from src.domain.viewpoints.viewpoint_derived_attribute_deferral import declares_signal_source  # noqa: PLC0415

    catalog = getattr(getattr(verifier, "_runtime_catalogs", None), "viewpoints", None)
    definition = catalog.get(slug) if catalog is not None else None
    if definition is not None and declares_signal_source(definition):
        raise ValueError(
            f"viewpoint '{slug}' declares a security-signal source; its styled output is "
            "classification-bearing and must not be persisted into a git-tracked diagram — "
            "use the ephemeral render and the stamped export instead"
        )


def create_diagram(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    diagram_type: str,
    name: str,
    puml: str,
    artifact_id: str | None,
    keywords: list[str] | None = None,
    diagram_entities: dict[str, object] | None = None,
    diagram_connections: list[dict[str, object]] | None = None,
    entity_ids_used: list[str] | None = None,
    connection_ids_used: list[str] | None = None,
    view_derivations: list[dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
    authored_groupings: list[dict[str, object]] | None = None,
    version: str,
    status: str,
    last_updated: str | None,
    tlp: str | None = None,
    viewpoint: dict[str, object] | None = None,
    connection_inference: DiagramConnectionInferenceMode = "none",
    auto_include_stereotypes: bool = True,
    dry_run: bool,
    group: str = UNCATEGORIZED,
) -> WriteResult:
    assert_engagement_write_root(repo_root)

    from src.application.modeling.binding_normalize import normalize_bindings, strip_diagram_shorthand
    from src.domain.diagrams.bindings import bindings_to_raw

    from .boundary import modification_stamp

    warnings: list[str] = []
    last = last_updated or modification_stamp()
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
    norm_bindings = normalize_bindings(diagram_entities, bindings)
    clean_entities = strip_diagram_shorthand(diagram_entities)
    norm_bindings_raw = bindings_to_raw(norm_bindings)

    # Workspace-id format check: all workspace entity ids in a new diagram are new.
    if diagram_entities is not None and isinstance(clean_entities, dict):
        from src.application.verification._workspace_identity_rules import (
            validate_workspace_entity_ids,  # noqa: PLC0415
        )
        try:
            _dt_module = verifier._runtime_catalogs.diagram_types.find_diagram_type(diagram_type)
        except Exception:  # noqa: BLE001
            _dt_module = None
        if _dt_module is not None:
            _ws_errors = validate_workspace_entity_ids(clean_entities, _dt_module, committed_ids=None)
            from src.config.settings import datatype_type_references_blocking  # noqa: PLC0415
            if _ws_errors and datatype_type_references_blocking():
                _dummy_id = artifact_id or "new-diagram"
                return WriteResult(
                    wrote=False,
                    path=repo_root / "diagram-catalog" / "diagrams" / f"{_dummy_id}.puml",
                    artifact_id=_dummy_id,
                    content=None,
                    warnings=warnings,
                    verification={
                        "path": f"{_dummy_id}.puml",
                        "file_type": "diagram",
                        "valid": False,
                        "issues": [
                            {"severity": "error", "code": "E335-fmt", "message": m, "location": _dummy_id}
                            for m in _ws_errors
                        ],
                    },
                )

    if diagram_entities is not None and not puml:
        build = _build_model_backed(
            diagram_type=diagram_type, name=name, repo_root=repo_root, diagram_entities=diagram_entities,
            diagram_connections=diagram_connections, norm_bindings=norm_bindings,
            norm_bindings_raw=norm_bindings_raw, effective_id=artifact_id,
            entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
            view_derivations=view_derivations,
        )
    else:
        build = _build_from_puml(
            diagram_type=diagram_type, name=name, repo_root=repo_root, puml=puml, effective_id=artifact_id,
            auto_include_stereotypes=auto_include_stereotypes,
            entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
        )
    effective_id = build.effective_id

    from src.domain.viewpoints.viewpoint_application_parsing import normalize_viewpoint_frontmatter

    viewpoint_fm = normalize_viewpoint_frontmatter(viewpoint, target_kind="diagram", target_id=effective_id)
    _refuse_signal_viewpoint_persistence(viewpoint_fm, verifier)

    content = format_diagram_puml(
        artifact_id=effective_id,
        diagram_type=diagram_type,
        name=name,
        version=version,
        status=status,
        last_updated=last,
        keywords=keywords,
        diagram_entities=clean_entities,
        diagram_connections=diagram_connections,
        entity_ids_used=build.entity_ids_used,
        connection_ids_used=build.connection_ids_used,
        view_derivations=view_derivations,
        bindings=bindings_to_raw(norm_bindings) if norm_bindings else None,
        authored_groupings=authored_groupings,
        puml_body=build.puml_body,
        tlp=tlp,
        viewpoint=viewpoint_fm,
        diagram_format_version=2 if diagram_type == "datatype" else None,
    )

    # Confidential assurance diagrams are redirected to a gitignored source root so their
    # source never reaches the shared catalog (mirrors G-f for the rendered output).
    if is_confidential_diagram_source(diagram_type, tlp):
        diag_src_root = diagram_source_confidential_root(repo_root)
        if not dry_run:
            ensure_confidential_gitignore(diag_src_root)
    else:
        diag_src_root = diagram_source_root(repo_root)
    path = (
        diag_src_root / f"{effective_id}.puml"
        if group == UNCATEGORIZED
        else diag_src_root / group / f"{effective_id}.puml"
    )

    friendly_slug = extract_friendly_slug(effective_id)
    repo = get_repository(repo_root)
    try:
        validate_diagram_unique(repo, diagram_type, friendly_slug)
    except ValueError as e:
        # Report validation error in preview/dry_run
        error_msg = str(e)
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=effective_id,
            content=None,
            warnings=[error_msg],
            verification={
                "valid": False,
                "issues": [
                    {
                        "severity": "error",
                        "code": "duplicate_artifact",
                        "message": error_msg,
                        "location": None,
                    }
                ],
            },
        )

    if dry_run:
        res = verify_content_in_temp_path(
            verifier=verifier,
            file_type="diagram",
            desired_name=path.name,
            content=content,
            support_repo_root=repo_root,
        )
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=effective_id,
            content=content,
            warnings=warnings,
            verification=_verification_to_dict(path, res),
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    prev = path.read_text(encoding="utf-8") if path.exists() else None
    path.write_text(content, encoding="utf-8")

    res = verifier.verify_diagram_file(path)
    if not res.valid:
        if prev is None:
            try:
                path.unlink()
            except OSError:
                pass
        else:
            path.write_text(prev, encoding="utf-8")
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=effective_id,
            content=content,
            warnings=warnings,
            verification=_verification_to_dict(path, res),
        )

    # Render PNG + SVG after successful write. A failure here is reported as an *issue*, not only
    # as a warning: the file was written and is valid, but its picture is the artifact people
    # actually look at, and a layout crash used to come back as `verification.valid: true` with a
    # Java stack trace buried in `warnings`. A caller — or a CI step — could not tell a rendered
    # diagram from one that wrote a stack trace to disk.
    render_failures = render_diagram_outputs(path, warnings)
    res.issues.extend(
        # E350 is the existing "PlantUML error" code the syntax verifier already emits; a layout
        # crash is the same class of fact, so it reuses it rather than minting a second vocabulary.
        Issue(Severity.ERROR, "E350", failure, str(path))
        for failure in render_failures
    )

    clear_repo_caches(path)

    return WriteResult(
        wrote=True,
        path=path,
        artifact_id=effective_id,
        content=None,
        warnings=warnings,
        verification=_verification_to_dict(path, res),
    )
