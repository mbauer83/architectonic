"""Viewpoint-dependency checks for the promotion workflow (D14): a promoted diagram/matrix
whose ``ViewpointApplication`` pins an engagement-only viewpoint definition, or a version the
enterprise repo lacks, blocks promotion — the exact-version rule is never silently
reinterpreted (D8). Two resolutions, keyed by viewpoint slug and supplied by the caller:
``"promote_alongside"`` (move the engagement definition into the enterprise catalog — only
valid when the enterprise catalog has no entry at all for the slug) and ``"repin"`` (rewrite
the promoted application(s) to the enterprise's current version — only valid when the
enterprise catalog already carries *some* version of the slug).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.domain.viewpoints.viewpoint_application_parsing import parse_viewpoint_application
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.domain.viewpoints.viewpoints import TargetKind, ViewpointCatalog
from src.infrastructure.viewpoint_declarations import (
    load_effective_viewpoint_catalog,
    load_viewpoint_catalog_file,
    viewpoint_declarations_path,
    write_viewpoint_catalog_file,
)
from src.infrastructure.write.artifact_write._promote_file_ops import rewrite_viewpoint_pin
from src.infrastructure.write.artifact_write.promote_schema_check import (
    _default_catalogs,
    _specialization_engagement_only,
)

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository
    from src.application.runtime_catalogs import RuntimeCatalogs
    from src.application.verification.artifact_verifier import ArtifactRegistry
    from src.domain.ontology_representation.specializations import SpecializationInfo

ViewpointResolution = Literal["promote_alongside", "repin"]
_DependencyStatus = Literal["ok", "engagement_only", "version_mismatch"]


@dataclass(frozen=True)
class ViewpointDependency:
    """One promoted diagram/matrix's ``ViewpointApplication``, checked against the
    enterprise repo's effective catalog."""

    target_id: str
    target_kind: TargetKind
    slug: str
    pinned_version: int
    status: _DependencyStatus
    enterprise_version: int | None


def _dependency_for(
    target_id: str, target_kind: TargetKind, extra: Mapping[str, object], *, ent_catalog: ViewpointCatalog
) -> ViewpointDependency | None:
    raw = extra.get("viewpoint")
    if raw is None:
        return None
    try:
        application = parse_viewpoint_application(raw, target_kind=target_kind, target_id=target_id)
    except ValueError:
        return None  # malformed application — the verifier's concern, not this check's
    if application is None:
        return None
    ent_def = ent_catalog.get(application.viewpoint_slug)
    status: _DependencyStatus = (
        "ok"
        if ent_def is not None and ent_def.version == application.pinned_version
        else "engagement_only"
        if ent_def is None
        else "version_mismatch"
    )
    return ViewpointDependency(
        target_id=target_id,
        target_kind=target_kind,
        slug=application.viewpoint_slug,
        pinned_version=application.pinned_version,
        status=status,
        enterprise_version=ent_def.version if ent_def is not None else None,
    )


def collect_viewpoint_dependencies(
    diagram_ids: list[str], *, repo: "ArtifactRepository", ent_root: Path
) -> list[ViewpointDependency]:
    """One entry per promoted diagram/matrix carrying a ``viewpoint:`` application — always
    populated (even when ``status == "ok"``) so a caller can surface every dependency, not
    just the blocking ones."""
    ent_catalog = load_effective_viewpoint_catalog([ent_root])
    deps: list[ViewpointDependency] = []
    for did in diagram_ids:
        rec = repo.get_diagram(did)
        if rec is None:
            continue
        target_kind: TargetKind = "matrix" if rec.diagram_type == "matrix" else "diagram"
        dep = _dependency_for(did, target_kind, rec.extra, ent_catalog=ent_catalog)
        if dep is not None:
            deps.append(dep)
    return deps


def _enterprise_known_specialization_slugs(
    entries: tuple["SpecializationInfo", ...], *, eng_root: Path, ent_root: Path
) -> frozenset[str]:
    return frozenset(
        entry.slug
        for entry in entries
        if not _specialization_engagement_only(entry, eng_root=eng_root, ent_root=ent_root)
    )


def _promote_alongside_errors(slug: str, *, eng_root: Path, ent_root: Path, catalogs: "RuntimeCatalogs") -> list[str]:
    """Validate the engagement's definition transitively against the enterprise catalogs
    (referenced specializations/attribute schemas, scope types, presentation capabilities) —
    D14's "promoted viewpoint definitions validate transitively"."""
    eng_def = load_effective_viewpoint_catalog([eng_root]).get(slug)
    if eng_def is None:
        return [f"viewpoint '{slug}': no engagement-repo definition found to promote alongside"]
    base = build_registry_snapshot(catalogs, [ent_root])
    snapshot = replace(
        base,
        known_specialization_slugs=_enterprise_known_specialization_slugs(
            catalogs.specializations.entries, eng_root=eng_root, ent_root=ent_root
        ),
    )
    issues = validate_viewpoint_definition(
        eng_def,
        mode="save",
        known_entity_types=snapshot.known_entity_types,
        known_connection_types=snapshot.known_connection_types,
        known_specialization_slugs=snapshot.known_specialization_slugs,
        entity_attribute_types=dict(snapshot.entity_attribute_types),
        connection_attribute_types=dict(snapshot.connection_attribute_types),
        symmetric_connection_types=snapshot.symmetric_connection_types,
        entity_type_infos=snapshot.entity_type_infos,
    )
    return [
        f"viewpoint '{slug}' (promoted alongside): {issue.code} at {issue.path}: {issue.message}"
        for issue in issues
        if issue.severity == "error"
    ]


def viewpoint_dependency_errors(
    deps: list[ViewpointDependency],
    *,
    eng_root: Path,
    ent_root: Path,
    catalogs: "RuntimeCatalogs | None" = None,
    resolutions: Mapping[str, ViewpointResolution] | None = None,
) -> list[str]:
    """Blocking errors for unresolved dependencies. ``engagement_only`` resolves only via
    ``"promote_alongside"`` (validated transitively); ``version_mismatch`` (enterprise has a
    different — older or newer — version) resolves only via ``"repin"``: a newer enterprise
    version never satisfies the check by itself (D14)."""
    resolved = resolutions or {}
    resolved_catalogs = catalogs or _default_catalogs()
    errors: list[str] = []
    checked_promote_alongside: set[str] = set()
    for dep in deps:
        if dep.status == "ok":
            continue
        resolution = resolved.get(dep.slug)
        if dep.status == "engagement_only":
            if resolution == "promote_alongside":
                if dep.slug not in checked_promote_alongside:
                    checked_promote_alongside.add(dep.slug)
                    errors.extend(
                        _promote_alongside_errors(
                            dep.slug, eng_root=eng_root, ent_root=ent_root, catalogs=resolved_catalogs
                        )
                    )
                continue
            errors.append(
                f"{dep.target_kind} {dep.target_id}: viewpoint '{dep.slug}' v{dep.pinned_version} is declared "
                "only in the engagement repo — promote the definition alongside "
                f"(viewpoint_resolutions: {{{dep.slug!r}: 'promote_alongside'}}) before promoting"
            )
        else:  # version_mismatch
            if resolution == "repin":
                continue
            errors.append(
                f"{dep.target_kind} {dep.target_id}: viewpoint '{dep.slug}' is pinned to version "
                f"{dep.pinned_version} but the enterprise repo has version {dep.enterprise_version} — a newer "
                "enterprise version does not satisfy promotion by itself; re-pin to the enterprise version as an "
                f"explicit promotion step (viewpoint_resolutions: {{{dep.slug!r}: 'repin'}})"
            )
    return errors


def apply_viewpoint_resolutions(
    deps: list[ViewpointDependency],
    resolutions: Mapping[str, ViewpointResolution] | None,
    *,
    engagement_root: Path,
    enterprise_root: Path,
    registry: "ArtifactRegistry",
    backups: list[tuple[Path, bytes | None]],
) -> None:
    """Execute-time application of the plan's resolved viewpoint dependencies: writes the
    promoted-alongside definitions into the enterprise catalog, and re-pins each affected
    promoted diagram/matrix's application to the enterprise's current version."""
    resolved = resolutions or {}
    promote_slugs = {
        dep.slug for dep in deps if dep.status == "engagement_only" and resolved.get(dep.slug) == "promote_alongside"
    }
    for slug in promote_slugs:
        eng_def = load_effective_viewpoint_catalog([engagement_root]).get(slug)
        if eng_def is None:
            continue
        catalog_path = viewpoint_declarations_path(enterprise_root)
        backups.append((catalog_path, catalog_path.read_bytes() if catalog_path.exists() else None))
        ent_own = load_viewpoint_catalog_file(enterprise_root)
        remaining = tuple(entry for entry in ent_own.entries if entry.slug != slug)
        write_viewpoint_catalog_file(enterprise_root, ViewpointCatalog(entries=(*remaining, eng_def)))
        # Complete the MOVE: a definition lives in exactly one tier, and the loaders'
        # ``enterprise | engagement`` union enforces that at every process start — an
        # engagement copy left behind would crash the next boot with a duplicate slug.
        # Engagement-side consumers keep resolving the slug through the enterprise
        # baseline, at the same version just promoted.
        eng_catalog_path = viewpoint_declarations_path(engagement_root)
        backups.append(
            (eng_catalog_path, eng_catalog_path.read_bytes() if eng_catalog_path.exists() else None)
        )
        eng_own = load_viewpoint_catalog_file(engagement_root)
        eng_remaining = tuple(entry for entry in eng_own.entries if entry.slug != slug)
        write_viewpoint_catalog_file(engagement_root, ViewpointCatalog(entries=eng_remaining))

    for dep in deps:
        if dep.status != "version_mismatch" or resolved.get(dep.slug) != "repin" or dep.enterprise_version is None:
            continue
        src = registry.find_file_by_id(dep.target_id)
        if src is None:
            continue
        dest = enterprise_root / src.relative_to(engagement_root)
        if dest.exists():
            rewrite_viewpoint_pin(dest, dep.enterprise_version)
