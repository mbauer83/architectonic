"""Verification logic for .outgoing.md connection files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification._verifier_rules_schema import (
    check_connection_metadata_schema,
    check_frontmatter_schema,
)
from src.application.verification._verifier_rules_semantic import check_connection_semantics
from src.application.verification.artifact_verifier_parsing import parse_frontmatter, read_file
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_rules import check_enum, check_required_fields
from src.application.verification.artifact_verifier_types import (
    OUTGOING_FILE_REQUIRED,
    VALID_STATUSES,
    Issue,
    Severity,
    VerificationResult,
)
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.specialization_values import applied_specialization_slugs
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.domain.repository.connection_declaration import (
    ConnectionDeclaration,
    parse_connection_declarations,
    parse_connection_header,
)

_MULTIPLICITY_RE = re.compile(r"^\d+$|^\d+\.\.\d+$|^\d+\.\.\*$|^\*$")


def _check_malformed_headers(content: str, result: VerificationResult, loc: str) -> None:
    """Emit E122 for every ``### `` line whose header doesn't match the grammar.

    ``parse_connection_declarations`` silently skips malformed sections (by design, for
    lenient reading elsewhere) — the verifier is the one caller that must still surface
    them, so this scans raw lines separately rather than relying on that parse.
    """
    for line in content.splitlines():
        if not line.startswith("### "):
            continue
        header = line[4:].strip()
        if parse_connection_header(header) is None:
            result.issues.append(
                Issue(Severity.ERROR, "E122", f"Connection header missing ' → ' separator: '{header}'", loc)
            )


def _target_issue(target_id: str, all_short_ids: set[str], scope: str, loc: str) -> Issue:
    """Distinguish an enterprise-scope leak (E130) from a genuinely missing target (E124)."""
    if stable_id(target_id) in all_short_ids and scope == "enterprise":
        return Issue(
            Severity.ERROR, "E130", f"enterprise connection references non-enterprise entity '{target_id}'", loc
        )
    return Issue(Severity.ERROR, "E124", f"Target entity '{target_id}' not found in model", loc)


def _check_source_entity(
    source: str,
    *,
    entity_short_ids: set[str],
    enterprise_short_ids: set[str],
    scope: str,
    result: VerificationResult,
    loc: str,
) -> None:
    """Validate that ``source-entity`` exists and respects enterprise scoping (E120/E131)."""
    source_short = stable_id(source)
    if source_short not in entity_short_ids:
        result.issues.append(Issue(Severity.ERROR, "E120", f"source-entity '{source}' not found in model", loc))
    elif scope == "enterprise" and source_short not in enterprise_short_ids:
        result.issues.append(
            Issue(Severity.ERROR, "E131", f"enterprise connection has non-enterprise source-entity '{source}'", loc)
        )


def _check_connection_specialization(
    slug: str,
    conn_type: str,
    catalog: SpecializationCatalog,
    result: VerificationResult,
    loc: str,
) -> None:
    """Unknown slug (E160) or slug declared for a different concept-kind/parent-type (E161)."""
    if catalog.get("connection", conn_type, slug) is not None:
        return
    matches = [e for e in catalog.entries if e.slug == slug]
    if not matches:
        result.issues.append(Issue(Severity.ERROR, "E160", f"Unknown specialization slug '{slug}'", loc))
        return
    declared_for = ", ".join(sorted({f"{e.concept_kind}/{e.parent_type}" for e in matches}))
    result.issues.append(
        Issue(
            Severity.ERROR,
            "E161",
            f"Specialization '{slug}' is not declared for connection type '{conn_type}' "
            f"(declared for: {declared_for}).",
            loc,
        )
    )


def _check_target_slug_drift(
    target_id: str,
    canonical_ids_by_short: dict[str, set[str]],
    result: VerificationResult,
    loc: str,
) -> None:
    """W121 — the target resolves, but names the entity by a slug it no longer has.

    Identity is the ``PREFIX@epoch.random`` stem, so this reference is not broken and every
    consumer resolves it: a warning, never an error. It is still worth reporting, because
    the slug is the only part of the id a reader can understand, and one naming a former
    title of the target is actively misleading in review — silence here is what let drift
    accumulate unnoticed.

    Silent when the stem is ambiguous: with more than one candidate there is no single
    "current" slug to name, and guessing would report drift against a correct reference.
    Ambiguity across tiers is diagnosed on its own by the resolver, not here.
    """
    candidates = canonical_ids_by_short.get(stable_id(target_id), set())
    if len(candidates) != 1:
        return
    canonical = next(iter(candidates))
    if canonical == target_id:
        return
    result.issues.append(
        Issue(
            Severity.WARNING,
            "W121",
            f"Connection target '{target_id}' names a stale slug; the entity is now "
            f"'{canonical}'. Resolution is unaffected — rewrite the reference to keep it readable.",
            loc,
        )
    )


def _check_connection_block(
    decl: ConnectionDeclaration,
    *,
    catalogs: RuntimeCatalogs,
    has_registry: bool,
    allowed_short_ids: set[str],
    all_short_ids: set[str],
    canonical_ids_by_short: dict[str, set[str]],
    scope: str,
    seen_connections: set[str],
    repo_root: Path | None,
    result: VerificationResult,
    loc: str,
) -> ConnectionDeclaration:
    """Validate a single parsed connection declaration, appending any issues.

    Malformed headers never reach here — ``_check_malformed_headers`` (E122) covers those
    separately, since ``parse_connection_declarations`` silently skips them.
    """
    conn_type, target_id = decl.conn_type, decl.target_id
    src_mult, tgt_mult = decl.src_multiplicity, decl.tgt_multiplicity
    if conn_type not in catalogs.ontology.all_connection_type_names():
        result.issues.append(Issue(Severity.ERROR, "E123", f"Unknown connection type '{conn_type}'", loc))
    for mult_label, mult_val in (("source", src_mult), ("target", tgt_mult)):
        if mult_val and not _MULTIPLICITY_RE.match(mult_val):
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E125",
                    f"Invalid {mult_label} multiplicity '{mult_val}' — expected n, n..m, n..*, or *",
                    loc,
                )
            )
    if has_registry and stable_id(target_id) not in allowed_short_ids:
        result.issues.append(_target_issue(target_id, all_short_ids, scope, loc))
    else:
        _check_target_slug_drift(target_id, canonical_ids_by_short, result, loc)

    conn_key = f"{conn_type} → {stable_id(target_id)}"
    if conn_key in seen_connections:
        result.issues.append(Issue(Severity.WARNING, "W120", f"Duplicate connection: '{conn_key}'", loc))
    seen_connections.add(conn_key)

    for slug in applied_specialization_slugs(decl.metadata.get("specialization")):
        _check_connection_specialization(slug, conn_type, catalogs.specializations, result, loc)

    if decl.metadata and repo_root is not None:
        check_connection_metadata_schema(
            decl.metadata, conn_type, repo_root, result, loc,
            specialization_catalog=catalogs.specializations,
            profile_registry=catalogs.profiles,
        )

    return decl


def verify_outgoing(
    path: Path,
    *,
    registry: ArtifactRegistry | None,
    catalogs: RuntimeCatalogs,
    scope: Literal["enterprise", "engagement", "unknown"],
    repo_root: Path | None,
) -> VerificationResult:
    """Verify a .outgoing.md file."""
    result = VerificationResult(path=path, file_type="connection")
    loc = str(path)
    content = read_file(path, result, loc)
    if content is None:
        return result
    fm = parse_frontmatter(content, result, loc)
    if fm is None:
        return result

    check_required_fields(fm, OUTGOING_FILE_REQUIRED, result, loc)
    check_enum(fm, "status", VALID_STATUSES, result, loc)

    source = fm.get("source-entity", "")
    if registry is not None:
        all_entity_ids = registry.entity_ids()
        ent_entity_ids = registry.enterprise_entity_ids()
        all_short_ids = {stable_id(e) for e in all_entity_ids}
        ent_short_ids = {stable_id(e) for e in ent_entity_ids}
        allowed_short_ids = ent_short_ids if scope == "enterprise" else all_short_ids
        # Short id → every full id carrying it, so a resolving reference can be compared
        # against the slug the target actually has (W121). A set, not a single value: the
        # engagement and enterprise tiers can both hold an entity with the same stem, and
        # picking one arbitrarily would report drift against a perfectly correct reference.
        canonical_ids_by_short: dict[str, set[str]] = {}
        for entity_id in all_entity_ids:
            canonical_ids_by_short.setdefault(stable_id(entity_id), set()).add(entity_id)
    else:
        all_short_ids = ent_short_ids = allowed_short_ids = set()
        canonical_ids_by_short = {}

    if source:
        if registry is not None:
            _check_source_entity(
                source,
                entity_short_ids=all_short_ids,
                enterprise_short_ids=ent_short_ids,
                scope=scope,
                result=result,
                loc=loc,
            )

    if "<!-- §connections -->" not in content:
        result.issues.append(
            Issue(Severity.ERROR, "E121", "Missing <!-- §connections --> section marker", loc)
        )

    _check_malformed_headers(content, result, loc)

    seen_connections: set[str] = set()
    parsed_connections: list[ConnectionDeclaration] = []
    for decl in parse_connection_declarations(content):
        parsed_connections.append(
            _check_connection_block(
                decl,
                catalogs=catalogs,
                has_registry=registry is not None,
                allowed_short_ids=allowed_short_ids,
                all_short_ids=all_short_ids,
                canonical_ids_by_short=canonical_ids_by_short,
                scope=scope,
                seen_connections=seen_connections,
                repo_root=repo_root,
                result=result,
                loc=loc,
            )
        )

    if registry is not None and source and parsed_connections:
        check_connection_semantics(
            source,
            parsed_connections,
            registry,
            result,
            loc,
            connections_catalog=catalogs.connections,
            ontology_catalog=catalogs.ontology,
            specialization_catalog=catalogs.specializations,
        )

    if repo_root is not None:
        check_frontmatter_schema(fm, repo_root, "outgoing", result, loc)

    return result
