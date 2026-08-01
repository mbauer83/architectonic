"""``persist_viewpoint_definition``/``delete_viewpoint_definition``: the one write path a
GUI save flow and the ``artifact_viewpoint`` MCP tool both go through for authoring
engagement-repo viewpoint definitions — ``persist_edit``-mode validation plus the
lifecycle rules against prior state: version bump on semantic edit, slug uniqueness
against the effective merged catalog, enterprise/module definitions read-only, delete
blocked while referenced.

Pure orchestration, no file I/O (hexagonal boundary: application never imports infrastructure
adapters directly) — callers load ``local_catalog`` via
``src.infrastructure.viewpoint_declarations.load_viewpoint_catalog_file`` and, when the
result is ``ok`` and not a dry run, persist ``result.catalog_to_write`` via
``write_viewpoint_catalog_file``. Referencer discovery (delete only) goes through the
``DiagramSearchAccess`` port, satisfied by the real read stores already.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Literal, Protocol

from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot, issue
from src.domain.viewpoints.viewpoint_lineage import fork_lineage
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue
from src.domain.viewpoints.viewpoints import TargetKind, ViewpointCatalog, ViewpointDefinition

PersistAction = Literal["create", "edit"]


class DiagramSearchAccess(Protocol):
    """Narrow read port for referencer discovery — the real stores (``ArtifactRepository``/
    ``ArtifactRegistry``) already satisfy this, so no new adapter is needed."""

    def list_diagrams(self) -> list[DiagramRecord]: ...


@dataclass(frozen=True)
class ViewpointReferencer:
    artifact_id: str
    target_kind: TargetKind


@dataclass(frozen=True)
class ViewpointPersistResult:
    ok: bool
    action: Literal["create", "edit", "delete"]
    slug: str
    version: int | None
    issues: tuple[ViewpointValidationIssue, ...] = ()
    referencers: tuple[ViewpointReferencer, ...] = ()
    catalog_to_write: ViewpointCatalog | None = None  # set iff ok — the caller persists this

    def as_answer(self, *, dry_run: bool) -> dict[str, object]:
        """This result as both transports answer with it.

        ``catalog_to_write`` is deliberately absent: it is the caller's instruction, not part of the
        answer, and a serialiser walking the dataclass would have published a whole catalogue on
        every write. ``dry_run`` is a parameter because it is the *request's* property, echoed back —
        the result does not know whether it was asked to commit.

        The REST route and the MCP tool each had this, identically, which is how a shape served by
        two transports drifts on one of them.
        """
        return {
            "ok": self.ok,
            "action": self.action,
            "slug": self.slug,
            "version": self.version,
            "dry_run": dry_run,
            "issues": [asdict(issue) for issue in self.issues],
            "referencers": [asdict(referencer) for referencer in self.referencers],
        }


def _validate(
    definition: ViewpointDefinition,
    *,
    registries: RegistrySnapshot,
    prior_definition: ViewpointDefinition | None,
    catalog: ViewpointCatalog,
) -> tuple[ViewpointValidationIssue, ...]:
    return validate_viewpoint_definition(
        definition,
        mode="persist_edit",
        known_entity_types=registries.known_entity_types,
        known_connection_types=registries.known_connection_types,
        known_specialization_slugs=registries.known_specialization_slugs,
        entity_attribute_types=dict(registries.entity_attribute_types),
        connection_attribute_types=dict(registries.connection_attribute_types),
        symmetric_connection_types=registries.symmetric_connection_types,
        entity_type_infos=registries.entity_type_infos,
        depth_cap=registries.depth_cap,
        prior_definition=prior_definition,
        catalog=catalog,
    )


def _read_only_or_unknown_issue(slug: str, *, exists_in_merged_catalog: bool) -> ViewpointValidationIssue:
    if exists_in_merged_catalog:
        return issue(
            "error", "read-only-definition", "/slug", f"{slug!r} is an enterprise/module definition — read-only here"
        )
    return issue("error", "unknown-slug", "/slug", f"no engagement-repo viewpoint definition named {slug!r}")


def _pinned_slug(diagram_extra: Mapping[str, object]) -> str | None:
    application = diagram_extra.get("viewpoint")
    return application.get("slug") if isinstance(application, dict) else None


def find_viewpoint_referencers(slug: str, *, read_access: DiagramSearchAccess) -> tuple[ViewpointReferencer, ...]:
    """Diagrams/matrices whose ``viewpoint:`` frontmatter pins this slug — matrices are
    diagram-type ``"matrix"`` records, not a separate artifact kind."""
    referencers = [
        ViewpointReferencer(
            artifact_id=diagram.artifact_id,
            target_kind="matrix" if diagram.diagram_type == "matrix" else "diagram",
        )
        for diagram in read_access.list_diagrams()
        if _pinned_slug(diagram.extra) == slug
    ]
    return tuple(sorted(referencers, key=lambda r: r.artifact_id))


def persist_viewpoint_definition(
    action: PersistAction,
    definition: ViewpointDefinition,
    *,
    local_catalog: ViewpointCatalog,
    merged_catalog: ViewpointCatalog,
    registries: RegistrySnapshot,
    fork_of: str | None = None,
    index_generation: int | None = None,
) -> ViewpointPersistResult:
    """``create``: rejects a slug already present anywhere in ``merged_catalog``. ``edit``:
    rejects a slug that is not present in ``local_catalog`` (unknown, or an enterprise/module
    definition that is read-only here). On success, ``result.catalog_to_write`` is the full
    updated local catalog — the caller's to persist (or discard, for a dry run).

    Lineage is stamped HERE and only here — the one service every authoring route (GUI
    Save-as and MCP alike) goes through. A create with ``fork_of`` records the origin's
    slug/version/content-digest (+ ``index_generation``); a plain create strips any
    client-supplied lineage (provenance is never self-asserted); an edit preserves the
    stored lineage verbatim (provenance is written once, never altered by later edits)."""
    local_definition = local_catalog.get(definition.slug)

    if action == "create":
        if merged_catalog.get(definition.slug) is not None:
            collision = issue(
                "error", "slug-collision", "/slug", f"a viewpoint named {definition.slug!r} already exists"
            )
            return ViewpointPersistResult(
                ok=False, action=action, slug=definition.slug, version=definition.version, issues=(collision,)
            )
        if fork_of is not None:
            origin = merged_catalog.get(fork_of)
            if origin is None:
                unknown_origin = issue(
                    "error", "unknown-fork-origin", "/forked_from", f"fork origin {fork_of!r} does not exist"
                )
                return ViewpointPersistResult(
                    ok=False, action=action, slug=definition.slug, version=definition.version, issues=(unknown_origin,)
                )
            definition = replace(definition, forked_from=fork_lineage(origin, index_generation))
        else:
            definition = replace(definition, forked_from=None)
        prior_definition = None
    else:
        if local_definition is None:
            exists_elsewhere = merged_catalog.get(definition.slug) is not None
            return ViewpointPersistResult(
                ok=False,
                action=action,
                slug=definition.slug,
                version=definition.version,
                issues=(_read_only_or_unknown_issue(definition.slug, exists_in_merged_catalog=exists_elsewhere),),
            )
        definition = replace(definition, forked_from=local_definition.forked_from)
        prior_definition = local_definition

    issues = _validate(definition, registries=registries, prior_definition=prior_definition, catalog=merged_catalog)
    if any(item.severity == "error" for item in issues):
        return ViewpointPersistResult(
            ok=False, action=action, slug=definition.slug, version=definition.version, issues=issues
        )

    remaining = tuple(d for d in local_catalog.entries if d.slug != definition.slug)
    new_catalog = ViewpointCatalog(remaining + (definition,))
    return ViewpointPersistResult(
        ok=True,
        action=action,
        slug=definition.slug,
        version=definition.version,
        issues=issues,
        catalog_to_write=new_catalog,
    )


def delete_viewpoint_definition(
    slug: str,
    *,
    local_catalog: ViewpointCatalog,
    merged_catalog: ViewpointCatalog,
    read_access: DiagramSearchAccess,
) -> ViewpointPersistResult:
    local_definition = local_catalog.get(slug)
    if local_definition is None:
        exists_elsewhere = merged_catalog.get(slug) is not None
        return ViewpointPersistResult(
            ok=False,
            action="delete",
            slug=slug,
            version=None,
            issues=(_read_only_or_unknown_issue(slug, exists_in_merged_catalog=exists_elsewhere),),
        )

    referencers = find_viewpoint_referencers(slug, read_access=read_access)
    if referencers:
        listed = ", ".join(r.artifact_id for r in referencers)
        blocked = issue("error", "delete-blocked-referenced", "/slug", f"referenced by: {listed}")
        return ViewpointPersistResult(
            ok=False,
            action="delete",
            slug=slug,
            version=local_definition.version,
            issues=(blocked,),
            referencers=referencers,
        )

    remaining = tuple(d for d in local_catalog.entries if d.slug != slug)
    return ViewpointPersistResult(
        ok=True, action="delete", slug=slug, version=None, catalog_to_write=ViewpointCatalog(remaining)
    )
