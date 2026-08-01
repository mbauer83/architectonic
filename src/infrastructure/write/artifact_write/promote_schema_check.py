"""Schema-superset verification for promotion from engagement to enterprise repo.

Promotion requires that engagement schemata are supersets of enterprise schemata:
every property and required field defined in the enterprise schema must also exist in the
engagement schema. Violations block the promotion and return human-readable error strings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from src.application.artifacts.schema import (
    load_attribute_schema,
    load_frontmatter_schema,
    load_specialization_attachment_schema,
)
from src.application.runtime_catalogs import RuntimeCatalogs
from src.config.workspace_paths import infer_repo_scope
from src.domain.ontology_representation.specializations import SpecializationInfo
from src.infrastructure.specialization_declarations import load_specialization_catalog_file

if TYPE_CHECKING:
    from src.application.artifacts.document_schema import DocumentSchema
    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactRegistry


def _default_catalogs() -> RuntimeCatalogs:
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


def _schema_superset_errors(
    eng_schema: dict[str, Any],
    ent_schema: dict[str, Any],
    scope: str,
) -> list[str]:
    """Return error strings if *eng_schema* is not a superset of *ent_schema*."""
    errors: list[str] = []
    missing_props = set(ent_schema.get("properties", {}).keys()) - set(eng_schema.get("properties", {}).keys())
    if missing_props:
        errors.append(
            f"{scope}: engagement schema is missing properties required by enterprise: "
            + ", ".join(sorted(missing_props))
        )
    missing_required = set(ent_schema.get("required", [])) - set(eng_schema.get("required", []))
    if missing_required:
        errors.append(
            f"{scope}: engagement schema does not mark as required: "
            + ", ".join(sorted(missing_required))
            + " (required by enterprise schema)"
        )
    return errors


def _compare_schema_pairs(
    keys: Iterable[str],
    *,
    load_ent: Callable[[str], dict[str, Any] | None],
    load_eng: Callable[[str], dict[str, Any] | None],
    missing_eng_msg: Callable[[str], str],
    scope_label: Callable[[str], str],
) -> list[str]:
    """For each key, compare the enterprise/engagement schema pair, collecting errors.

    A key with no enterprise schema is skipped; one whose enterprise schema exists but
    whose engagement counterpart is absent yields ``missing_eng_msg(key)``.
    """
    errors: list[str] = []
    for key in keys:
        ent_s = load_ent(key)
        if ent_s is None:
            continue
        eng_s = load_eng(key)
        if eng_s is None:
            errors.append(missing_eng_msg(key))
            continue
        errors.extend(_schema_superset_errors(eng_s, ent_s, scope_label(key)))
    return errors


def _attribute_schema_errors(
    eng_root: Path, ent_root: Path, entity_ids: list[str], repo: "ArtifactRepository"
) -> list[str]:
    types = sorted({rec.artifact_type for eid in entity_ids if (rec := repo.get_entity(eid)) is not None})
    return _compare_schema_pairs(
        types,
        load_ent=lambda atype: load_attribute_schema(ent_root, atype),
        load_eng=lambda atype: load_attribute_schema(eng_root, atype),
        missing_eng_msg=lambda atype: (
            f"attribute profile '{atype}': engagement repo missing schema — "
            f"add .arch-repo/schemata/attributes.{atype}.schema.json"
        ),
        scope_label=lambda atype: f"attribute profile '{atype}'",
    )


def _specialization_engagement_only(entry: SpecializationInfo, *, eng_root: Path, ent_root: Path) -> bool:
    """True when *entry* is declared only in the engagement repo's own `specializations.yaml` —

    not shipped by the ontology module (module-shipped entries never appear in a repo's own
    declarations file at all, so they can never test positive here) and not independently
    declared in the enterprise repo's own file either."""
    eng_keys = {e.key for e in load_specialization_catalog_file(eng_root, entry.module_alias).entries}
    if entry.key not in eng_keys:
        return False
    ent_keys = {e.key for e in load_specialization_catalog_file(ent_root, entry.module_alias).entries}
    return entry.key not in ent_keys


def _specialization_attachment_errors(
    entry: SpecializationInfo, artifact_type: str, slug: str, eng_root: Path, ent_root: Path
) -> list[str]:
    """Superset-check the specialization's attachment schema file, if any.

    A specialization's profile is one-to-one with it (inline `attributes:` or this
    attachment file) — never a separately reusable, named registry entry — so there is no
    independent "named profile" to check beyond the specialization itself (already covered
    by `_specialization_engagement_only`) and this attachment file.
    """
    errors: list[str] = []
    ent_attachment = load_specialization_attachment_schema(ent_root, artifact_type, slug)
    if ent_attachment is not None:
        scope = f"specialization attachment schema '{artifact_type}.{slug}'"
        eng_attachment = load_specialization_attachment_schema(eng_root, artifact_type, slug)
        if eng_attachment is None:
            errors.append(
                f"{scope}: engagement repo missing schema — "
                f"add .arch-repo/schemata/attributes.{artifact_type}.{slug}.schema.json"
            )
        else:
            errors.extend(_schema_superset_errors(eng_attachment, ent_attachment, scope))
    return errors


def _specialization_dependency_errors(
    kind: Literal["entity", "connection"],
    parent_type: str,
    slug: str,
    label: str,
    *,
    eng_root: Path,
    ent_root: Path,
    catalogs: RuntimeCatalogs,
) -> list[str]:
    entry = catalogs.specializations.get(kind, parent_type, slug)
    if entry is None:
        # Unknown anywhere — E160/E170 (unknown specialization) is the verifier's concern,
        # not this promotion-superset check's.
        return []
    if _specialization_engagement_only(entry, eng_root=eng_root, ent_root=ent_root):
        return [
            f"{kind} specialization '{slug}' (type '{parent_type}', {label}): declared only in the "
            "engagement repo's .arch-repo/specializations.yaml — add it to the enterprise repo's "
            "specializations.yaml (or ship it in the ontology module) before promoting"
        ]
    if kind == "entity":
        return _specialization_attachment_errors(entry, parent_type, slug, eng_root, ent_root)
    return []


def _specialization_errors(
    eng_root: Path,
    ent_root: Path,
    entity_ids: list[str],
    connection_ids: list[str],
    repo: "ArtifactRepository",
    catalogs: RuntimeCatalogs,
) -> list[str]:
    errors: list[str] = []
    for eid in entity_ids:
        rec = repo.get_entity(eid)
        if rec is None:
            continue
        # Each applied specialization is a separate schema dependency across the tier boundary.
        for slug in rec.specializations:
            errors.extend(
                _specialization_dependency_errors(
                    "entity", rec.artifact_type, slug, f"entity {eid}",
                    eng_root=eng_root, ent_root=ent_root, catalogs=catalogs,
                )
            )
    for cid in connection_ids:
        conn = repo.get_connection(cid)
        if conn is None:
            continue
        for slug in conn.specializations:
            errors.extend(
                _specialization_dependency_errors(
                    "connection", conn.conn_type, slug, f"connection {cid}",
                    eng_root=eng_root, ent_root=ent_root, catalogs=catalogs,
                )
            )
    return errors


def _frontmatter_schema_errors(
    eng_root: Path, ent_root: Path, has_entities: bool, has_diagrams: bool
) -> list[str]:
    file_types = (["entity", "outgoing"] if has_entities else []) + (["diagram"] if has_diagrams else [])
    return _compare_schema_pairs(
        file_types,
        load_ent=lambda ft: load_frontmatter_schema(ent_root, ft),
        load_eng=lambda ft: load_frontmatter_schema(eng_root, ft),
        missing_eng_msg=lambda ft: (
            f"frontmatter schema '{ft}': engagement repo missing schema — "
            f"add .arch-repo/schemata/frontmatter.{ft}.schema.json"
        ),
        scope_label=lambda ft: f"frontmatter '{ft}'",
    )


def _document_section_errors(doc_type: str, ent_ds: "DocumentSchema", eng_ds: "DocumentSchema") -> list[str]:
    """Compare normalized section specs: engagement must cover every enterprise section and,

    for sections present in both, require at least the same entity-type connection terms.
    """
    errors: list[str] = []
    eng_sections = {section.name: section for section in eng_ds.sections}
    missing_sections = [section.name for section in ent_ds.sections if section.name not in eng_sections]
    if missing_sections:
        errors.append(
            f"document schema '{doc_type}': engagement schema missing required sections: "
            + ", ".join(sorted(missing_sections))
        )
    for ent_section in ent_ds.sections:
        eng_section = eng_sections.get(ent_section.name)
        if eng_section is None:
            continue
        missing_terms = set(ent_section.required_entity_type_connections) - set(
            eng_section.required_entity_type_connections
        )
        if missing_terms:
            errors.append(
                f"document schema '{doc_type}': section '{ent_section.name}' engagement schema does not "
                "require entity-type connections: " + ", ".join(sorted(missing_terms))
                + " (required by enterprise schema)"
            )
    return errors


def _document_schema_errors(
    eng_root: Path, ent_root: Path, document_ids: list[str], repo: "ArtifactRepository"
) -> list[str]:
    if not document_ids:
        return []
    from src.application.artifacts.document_schema import get_document_schema_object

    doc_types = sorted({doc.doc_type for did in document_ids if (doc := repo.get_document(did)) is not None})
    errors: list[str] = []
    for doc_type in doc_types:
        ent_ds = get_document_schema_object(ent_root, doc_type)
        if ent_ds is None:
            continue
        eng_ds = get_document_schema_object(eng_root, doc_type)
        if eng_ds is None:
            errors.append(
                f"document schema '{doc_type}': engagement repo missing schema — "
                f"add .arch-repo/documents/{doc_type}.json"
            )
            continue
        ent_fm: dict[str, object] = ent_ds.data.get("frontmatter_schema") or {}
        eng_fm: dict[str, object] = eng_ds.data.get("frontmatter_schema") or {}
        if ent_fm:
            errors.extend(_schema_superset_errors(eng_fm, ent_fm, f"document frontmatter '{doc_type}'"))
        errors.extend(_document_section_errors(doc_type, ent_ds, eng_ds))
    return errors


def check_promotion_schema_compatibility(
    entity_ids: list[str],
    has_diagrams: bool,
    document_ids: list[str],
    registry: "ArtifactRegistry",
    repo: "ArtifactRepository",
    connection_ids: list[str] | None = None,
    catalogs: RuntimeCatalogs | None = None,
) -> list[str]:
    """Check that engagement schemata are supersets of enterprise schemata.

    Inspects attribute profiles, frontmatter schemas, document schemas, and — for entities
    and connections carrying a specialization — the specialization itself plus its attached
    schema/named-profile, for all artifact types present in the promotion set.

    Returns a list of blocking error strings (empty = no violations).
    """
    eng_roots = [r for r in registry.repo_roots if infer_repo_scope(r) != "enterprise"]
    ent_roots = [r for r in registry.repo_roots if infer_repo_scope(r) == "enterprise"]
    if not eng_roots or not ent_roots:
        return []
    eng_root, ent_root = eng_roots[0], ent_roots[0]

    return [
        *_attribute_schema_errors(eng_root, ent_root, entity_ids, repo),
        *_specialization_errors(
            eng_root, ent_root, entity_ids, connection_ids or [], repo, catalogs or _default_catalogs()
        ),
        *_frontmatter_schema_errors(eng_root, ent_root, bool(entity_ids), has_diagrams),
        *_document_schema_errors(eng_root, ent_root, document_ids, repo),
    ]
