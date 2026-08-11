"""Plan-time reference closure for promotion: refuse before writing, and name the artifact.

The single promotion invariant is *after promotion the enterprise repository must
verify*. The staged-repo verification enforces that after the copy — but a selection
that is knowably incomplete (a document whose schema-required entity link stays
engagement-side, a diagram binding an entity or connection that will not exist
enterprise-side) should be refused at plan time, with the missing artifact identified,
instead of rolling the whole promotion back with an error that names nothing.

Closure is over the *selected set*, never transitive reachability: each artifact in
the set must have its required references satisfied by the set or by the enterprise
repository. The records are STRUCTURED so surfaces can offer a one-action "add the
missing artifact to the set" flow; the prose errors derived from them keep non-GUI
callers blocked with the same facts (mirroring the structural-closure precedent).

Deliberately NOT offered here: a "repin"-style resolution. Re-targeting a document
citation or a diagram's entity reference would change what the artifact says; the
only resolutions are promote-alongside or drop-from-set.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from src.application.artifacts.document_schema import get_document_schema
from src.application.verification._verifier_document import (
    ResolvedEntityLink,
    document_body,
    document_section_spans,
    resolve_entity_links,
)
from src.domain.artifact_id import (
    MalformedArtifactIdError,
    connection_id_as_written,
    stable_conn_id,
    stable_id,
)
from src.domain.repository.frontmatter import parse_frontmatter

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository
    from src.application.runtime_catalogs import RuntimeCatalogs
    from src.application.verification.artifact_verifier import ArtifactRegistry

DependencyKind = Literal[
    "document_required_link",
    "diagram_entity",
    "diagram_connection_endpoint",
    "diagram_connection",
    "diagram_binding_target",
]

@dataclass(frozen=True)
class MissingDependency:
    """One reference a selected artifact requires that promotion would leave dangling."""

    artifact_id: str
    name: str
    record_type: Literal["entity", "connection"]
    required_by: str
    kind: DependencyKind


@dataclass(frozen=True)
class _ClosureScope:
    """Membership predicates shared by every per-artifact closure check."""

    set_entity_short: frozenset[str]
    enterprise_entity_short: frozenset[str]
    set_diagram_ids: frozenset[str]
    enterprise_diagram_ids: frozenset[str]
    enterprise_connection_short: frozenset[str]

    def entity_satisfied(self, entity_id: str) -> bool:
        short = stable_id(entity_id)
        return (
            short in self.set_entity_short
            or short in self.enterprise_entity_short
            or entity_id.startswith("GAR@")
        )

    def diagram_satisfied(self, diagram_id: str) -> bool:
        return diagram_id in self.set_diagram_ids or diagram_id in self.enterprise_diagram_ids


def compute_reference_closure(
    *,
    document_ids: list[str],
    diagram_ids: list[str],
    promoted_entity_ids: set[str],
    repo: "ArtifactRepository",
    registry: "ArtifactRegistry",
    engagement_root: Path,
    catalogs: "RuntimeCatalogs",
) -> list[MissingDependency]:
    """Missing required references for every selected document and diagram."""
    scope = _ClosureScope(
        set_entity_short=frozenset(stable_id(e) for e in promoted_entity_ids),
        enterprise_entity_short=frozenset(stable_id(e) for e in registry.enterprise_entity_ids()),
        set_diagram_ids=frozenset(diagram_ids),
        enterprise_diagram_ids=frozenset(registry.enterprise_diagram_ids()),
        enterprise_connection_short=frozenset(
            stable_conn_id(c) for c in registry.enterprise_connection_ids()
        ),
    )
    missing: list[MissingDependency] = []
    for doc_id in document_ids:
        missing.extend(
            _document_missing(
                doc_id, registry=registry, engagement_root=engagement_root,
                catalogs=catalogs, scope=scope, repo=repo,
            )
        )
    for diagram_id in diagram_ids:
        missing.extend(_diagram_missing(diagram_id, registry=registry, repo=repo, scope=scope))
    return _deduplicate(missing)


def missing_dependency_errors(missing: list[MissingDependency]) -> list[str]:
    """Blocking prose for the same facts — every message names the missing artifact."""
    kind_phrases: dict[DependencyKind, str] = {
        "document_required_link": "links it to satisfy a schema-required entity-type connection",
        "diagram_entity": "binds it in entity-ids-used",
        "diagram_connection_endpoint": "binds a connection whose endpoint it is",
        "diagram_connection": "binds it in connection-ids-used",
        "diagram_binding_target": "targets it in a diagram binding",
    }
    return [
        f"Missing promotion dependency: {dep.required_by} requires {dep.artifact_id} "
        f"('{dep.name}') — it {kind_phrases[dep.kind]}, but it is neither in the promotion "
        "set nor in the enterprise repository. Add it to the set or remove the referencing "
        "artifact from the selection."
        for dep in missing
    ]


def _deduplicate(missing: list[MissingDependency]) -> list[MissingDependency]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[MissingDependency] = []
    for dep in missing:
        key = (dep.artifact_id, dep.required_by, dep.kind)
        if key not in seen:
            seen.add(key)
            unique.append(dep)
    return unique


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def _document_missing(
    doc_id: str,
    *,
    registry: "ArtifactRegistry",
    engagement_root: Path,
    catalogs: "RuntimeCatalogs",
    scope: _ClosureScope,
    repo: "ArtifactRepository",
) -> list[MissingDependency]:
    path = registry.find_file_by_id(doc_id)
    doc = repo.get_document(doc_id)
    if path is None or doc is None:
        return []
    schema = get_document_schema(engagement_root, doc.doc_type)
    if schema is None:
        return []
    content = path.read_text(encoding="utf-8")

    missing = _missing_for_required_terms(
        terms=schema.get("required_entity_type_connections") or [],
        links=resolve_entity_links(path, content),
        doc_id=doc_id, catalogs=catalogs, scope=scope,
    )
    spans = document_section_spans(document_body(content))
    for section in schema.get("sections") or []:
        name = str(section.get("name") or "").strip()
        terms: list[str] = section.get("required_entity_type_connections") or []
        if name and terms and name in spans:
            missing.extend(
                _missing_for_required_terms(
                    terms=terms,
                    links=resolve_entity_links(path, spans[name]),
                    doc_id=doc_id, catalogs=catalogs, scope=scope,
                )
            )
    return missing


def _missing_for_required_terms(
    *,
    terms: list[str],
    links: list[ResolvedEntityLink],
    doc_id: str,
    catalogs: "RuntimeCatalogs",
    scope: _ClosureScope,
) -> list[MissingDependency]:
    """For each required term: if no satisfying linked entity survives promotion,
    every linked entity that *would* satisfy it is a missing dependency."""
    ontology = catalogs.ontology
    missing: list[MissingDependency] = []
    for term in terms:
        candidates = [
            link
            for link in links
            if link.artifact_id and ontology.entity_type_term_matches(term, {link.artifact_type})
        ]
        if not candidates:
            continue  # nothing links this term at all — the engagement verifier's finding
        if any(scope.entity_satisfied(link.artifact_id) for link in candidates):
            continue
        missing.extend(
            MissingDependency(
                artifact_id=link.artifact_id,
                name=link.name,
                record_type="entity",
                required_by=doc_id,
                kind="document_required_link",
            )
            for link in candidates
        )
    return missing


# ---------------------------------------------------------------------------
# Diagrams
# ---------------------------------------------------------------------------


def _diagram_frontmatter(path: Path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _hosted_element_ids(fm: dict) -> set[str]:
    """Element ids the diagram hosts itself (diagram-entities) — closed by the file copy."""
    de = fm.get("diagram-entities")
    if not isinstance(de, dict):
        return set()
    return {
        str(item["id"])
        for items in de.values()
        if isinstance(items, list)
        for item in items
        if isinstance(item, dict) and item.get("id") is not None
    }


def _split_connection_id(cid: str) -> tuple[str, str] | None:
    """(source, target) from the canonical ``SRC---TGT@@type`` connection id form."""
    if "---" not in cid or "@@" not in cid:
        return None
    try:
        source, target, _conn_type = connection_id_as_written(cid)
    except MalformedArtifactIdError:
        return None
    return (source.strip(), target.strip()) if source and target else None


def _missing_entity(
    entity_id: str,
    diagram_id: str,
    kind: DependencyKind,
    *,
    repo: "ArtifactRepository",
    scope: _ClosureScope,
) -> MissingDependency | None:
    """A missing-dependency record for *entity_id*, or None when it is satisfied.

    A diagram-only entity is satisfied through its HOST diagram: its file content
    travels with the host, so the host being in the set or enterprise closes it.
    """
    if scope.entity_satisfied(entity_id):
        return None
    record = repo.get_entity(entity_id) or repo.find_entity_by_workspace_id(entity_id)
    host = getattr(record, "host_diagram_id", None) if record is not None else None
    if host and scope.diagram_satisfied(str(host)):
        return None
    return MissingDependency(
        artifact_id=entity_id,
        name=record.name if record is not None else entity_id,
        record_type="entity",
        required_by=diagram_id,
        kind=kind,
    )


def _missing_for_connection(
    cid: str,
    diagram_id: str,
    *,
    repo: "ArtifactRepository",
    scope: _ClosureScope,
) -> list[MissingDependency]:
    """A bound connection must exist enterprise-side after the copy: either it already
    does, or its source entity is promoted (its outgoing file travels along) with the
    target resolvable. A connection surviving on neither path is itself missing."""
    if stable_conn_id(cid) in scope.enterprise_connection_short:
        return []
    endpoints = _split_connection_id(cid)
    if endpoints is None:
        return []  # unparseable id — the verifier's E302, not a closure fact
    source, target = endpoints
    missing = [
        dep
        for entity_id in (source, target)
        if (dep := _missing_entity(entity_id, diagram_id, "diagram_connection_endpoint", repo=repo, scope=scope))
        is not None
    ]
    if not missing and stable_id(source) not in scope.set_entity_short:
        missing.append(
            MissingDependency(
                artifact_id=cid,
                name=cid,
                record_type="connection",
                required_by=diagram_id,
                kind="diagram_connection",
            )
        )
    return missing


def _binding_target_refs(fm: dict) -> tuple[list[str], list[str]]:
    """Model entity/connection ids referenced by top-level binding targets."""
    entity_refs: list[str] = []
    connection_refs: list[str] = []
    for raw in fm.get("bindings") or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("target"), dict):
            continue
        target = raw["target"]
        if target.get("entity_id") is not None:
            entity_refs.append(str(target["entity_id"]))
        if target.get("connection_id") is not None:
            connection_refs.append(str(target["connection_id"]))
        for cid in target.get("connection_ids") or []:
            connection_refs.append(str(cid))
    return entity_refs, connection_refs


def _diagram_missing(
    diagram_id: str,
    *,
    registry: "ArtifactRegistry",
    repo: "ArtifactRepository",
    scope: _ClosureScope,
) -> list[MissingDependency]:
    path = registry.find_file_by_id(diagram_id)
    if path is None:
        return []
    fm = _diagram_frontmatter(path)
    hosted = _hosted_element_ids(fm)
    missing: list[MissingDependency] = []

    entity_ids = fm.get("entity-ids-used")
    for eid in entity_ids if isinstance(entity_ids, list) else []:
        eid_str = str(eid)
        if eid_str in hosted:
            continue
        dep = _missing_entity(eid_str, diagram_id, "diagram_entity", repo=repo, scope=scope)
        if dep is not None:
            missing.append(dep)

    conn_ids = fm.get("connection-ids-used")
    for cid in conn_ids if isinstance(conn_ids, list) else []:
        missing.extend(_missing_for_connection(str(cid), diagram_id, repo=repo, scope=scope))

    entity_refs, connection_refs = _binding_target_refs(fm)
    for eid_str in entity_refs:
        if eid_str in hosted:
            continue
        dep = _missing_entity(eid_str, diagram_id, "diagram_binding_target", repo=repo, scope=scope)
        if dep is not None:
            missing.append(dep)
    for cid_str in connection_refs:
        if stable_conn_id(cid_str) not in scope.enterprise_connection_short:
            missing.extend(_missing_for_connection(cid_str, diagram_id, repo=repo, scope=scope))

    return missing
