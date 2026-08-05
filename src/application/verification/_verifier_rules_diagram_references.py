"""What a diagram's frontmatter claims to draw, checked against what the repository holds.

``entity-ids-used`` and ``connection-ids-used`` are the diagram's binding surface: the reconcile
path, the index and every reader take them as the list of what the picture is about. So each entry
has to name something that exists, something this tier is allowed to reference, and — for a
baselined diagram — something baselined.

It also has to name it *readably*. A reference holding a former slug resolves like any other, because
identity is the stem, so nothing here was ever reported: `artifact_verify` answered 0 warnings over
16 stale entity references across 6 diagrams, and the drift was invisible for exactly as long as
nobody looked. The connection files had that check (W121) from the start; the diagrams did not, which
is the only reason the two sides differ. They now read the same rule.

Its own module because `artifact_verifier_rules.py` had reached the file limit holding three
concerns — generic frontmatter fields, diagram references, PUML structure — and this is the one with
its own vocabulary.
"""

from __future__ import annotations

from typing import Literal

from src.application.derivation.strategy_registry import DerivationStrategyCatalog
from src.application.verification._verifier_rules_bindings import check_bindings_scoped, get_allowed_bindings
from src.application.verification._verifier_rules_view_derivations import check_all_view_derivations
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.artifact_id import (
    canonical_ids_by_stem,
    current_connection_spelling,
    current_spelling_of,
    stable_conn_id,
    stable_id,
)
from src.domain.modules.catalogs import DiagramTypeCatalog


def check_diagram_references_scoped(
    fm: dict,
    registry: ArtifactRegistry,
    file_scope: Literal["enterprise", "engagement", "unknown"],
    result: VerificationResult,
    loc: str,
    diagram_type_catalog: DiagramTypeCatalog | None = None,
    derivation_catalog: DerivationStrategyCatalog | None = None,
) -> None:
    diagram_is_baselined = str(fm.get("status", "")) == "baselined"

    allowed_entities = registry.enterprise_entity_ids() if file_scope == "enterprise" else registry.entity_ids()
    allowed_connections = (
        registry.enterprise_connection_ids() if file_scope == "enterprise" else registry.connection_ids()
    )
    all_entities = registry.entity_ids()
    all_connections = registry.connection_ids()

    _check_entity_ids_used(
        fm,
        registry,
        file_scope,
        allowed_entities,
        all_entities,
        diagram_is_baselined,
        result,
        loc,
    )
    _check_connection_ids_used(
        fm,
        registry,
        file_scope,
        allowed_connections,
        all_connections,
        diagram_is_baselined,
        result,
        loc,
    )
    check_all_view_derivations(fm, result, loc, catalog=derivation_catalog)
    check_bindings_scoped(
        fm, file_scope,
        allowed_entities, allowed_connections,
        all_entities, all_connections,
        result, loc,
        allowed_bindings=get_allowed_bindings(str(fm.get("diagram-type", "")), diagram_type_catalog),
    )


def _report_stale_slug(
    reference: str,
    current: str | None,
    *,
    code: str,
    field: str,
    result: VerificationResult,
    loc: str,
) -> None:
    """W305/W306 — the reference resolves, but names the artifact by a slug it no longer has."""
    if current is None:
        return
    result.issues.append(
        Issue(
            Severity.WARNING,
            code,
            f"{field} names '{reference}' by a stale slug; it should read '{current}'. Resolution is "
            "unaffected — rewrite the reference to keep the diagram readable.",
            loc,
        )
    )


def _check_entity_ids_used(
    fm: dict,
    registry: ArtifactRegistry,
    file_scope: Literal["enterprise", "engagement", "unknown"],
    allowed_entities: set[str],
    all_entities: set[str],
    diagram_is_baselined: bool,
    result: VerificationResult,
    loc: str,
) -> None:
    if "entity-ids-used" not in fm:
        return
    entity_ids = fm["entity-ids-used"]
    if not isinstance(entity_ids, list):
        if entity_ids is not None:
            result.issues.append(Issue(Severity.WARNING, "W303", "entity-ids-used should be a YAML list", loc))
        return

    allowed_short = {stable_id(a) for a in allowed_entities}
    all_short = {stable_id(a) for a in all_entities}
    canonical_entities = canonical_ids_by_stem(all_entities)
    for eid in entity_ids:
        eid_str = str(eid)
        eid_short = stable_id(eid_str)
        if eid_short not in allowed_short:
            issue = (
                Issue(
                    Severity.ERROR,
                    "E310",
                    (
                        f"entity-ids-used references non-enterprise entity '{eid_str}' "
                        "— enterprise diagrams may only reference enterprise entities"
                    ),
                    loc,
                )
                if eid_short in all_short and file_scope == "enterprise"
                else Issue(
                    Severity.ERROR,
                    "E301",
                    f"entity-ids-used references unknown entity '{eid_str}'",
                    loc,
                )
            )
            result.issues.append(issue)
            continue
        if diagram_is_baselined and registry.entity_status(eid_str) == "draft":
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E306",
                    (
                        "baselined diagram references draft entity "
                        f"'{eid_str}' — all entities in a baselined diagram "
                        "must be baselined"
                    ),
                    loc,
                )
            )
        _report_stale_slug(
            eid_str, current_spelling_of(eid_str, canonical_entities),
            code="W305", field="entity-ids-used", result=result, loc=loc,
        )


def _check_connection_ids_used(
    fm: dict,
    registry: ArtifactRegistry,
    file_scope: Literal["enterprise", "engagement", "unknown"],
    allowed_connections: set[str],
    all_connections: set[str],
    diagram_is_baselined: bool,
    result: VerificationResult,
    loc: str,
) -> None:
    if "connection-ids-used" not in fm:
        return
    conn_ids = fm["connection-ids-used"]
    if not isinstance(conn_ids, list):
        if conn_ids is not None:
            result.issues.append(Issue(Severity.WARNING, "W304", "connection-ids-used should be a YAML list", loc))
        return

    allowed_short_conns = {stable_conn_id(c) for c in allowed_connections}
    all_short_conns = {stable_conn_id(c) for c in all_connections}
    # The entity index, not the connection one: a connection is keyed by its endpoints' stems and
    # its type, so the registry holds no slugged spelling to compare against. What goes stale in a
    # `connection-ids-used` entry is the slug of one of its endpoints.
    canonical_entities = canonical_ids_by_stem(registry.entity_ids())
    for cid in conn_ids:
        cid_str = str(cid)
        cid_stable = stable_conn_id(cid_str)
        if cid_stable not in allowed_short_conns:
            issue = (
                Issue(
                    Severity.ERROR,
                    "E320",
                    (
                        f"connection-ids-used references non-enterprise connection '{cid_str}' "
                        "— enterprise diagrams may only reference enterprise connections"
                    ),
                    loc,
                )
                if cid_stable in all_short_conns and file_scope == "enterprise"
                else Issue(
                    Severity.ERROR,
                    "E302",
                    f"connection-ids-used references unknown connection '{cid_str}'",
                    loc,
                )
            )
            result.issues.append(issue)
            continue
        if diagram_is_baselined and registry.connection_status(cid_str) == "draft":
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E307",
                    (
                        f"baselined diagram references draft connection '{cid_str}' — "
                        "all connections in a baselined diagram must be baselined"
                    ),
                    loc,
                )
            )
        _report_stale_slug(
            cid_str, current_connection_spelling(cid_str, canonical_entities),
            code="W306", field="connection-ids-used", result=result, loc=loc,
        )
