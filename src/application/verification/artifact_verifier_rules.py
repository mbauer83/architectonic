import re
from typing import Literal

from src.application.artifact_parsing import extract_declared_puml_aliases as _extract_declared_puml_aliases_shared
from src.application.derivation.strategy_registry import DerivationStrategyCatalog
from src.application.verification._verifier_rules_bindings import check_bindings_scoped, get_allowed_bindings
from src.application.verification._verifier_rules_puml_relations import (
    _extract_entity_display_alias,
    _normalize_puml_alias,
)
from src.application.verification._verifier_rules_view_derivations import check_all_view_derivations
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import (
    DIAGRAM_ARTIFACT_TYPES,
    ENTITY_ID_RE,
    Issue,
    Severity,
    VerificationResult,
    entity_id_from_path,
)
from src.domain.artifact_id import stable_conn_id, stable_id
from src.domain.modules.catalogs import DiagramTypeCatalog
from src.domain.repository.repo_layout import MODEL


def check_required_fields(fm: dict, required: frozenset[str], result: VerificationResult, loc: str) -> None:
    for field_name in sorted(required):
        if field_name not in fm or fm[field_name] is None:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E021",
                    f"Required frontmatter field '{field_name}' is missing or null",
                    loc,
                )
            )


def check_artifact_id_entity(fm: dict, result: VerificationResult, loc: str) -> None:
    if "artifact-id" not in fm:
        return
    aid = str(fm["artifact-id"])
    if not ENTITY_ID_RE.match(aid):
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E101",
                f"artifact-id '{aid}' does not match TYPE@epoch.random.name pattern",
                loc,
            )
        )
        return

    file_id = entity_id_from_path(result.path)
    if file_id != aid:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E104",
                f"entity filename stem '{file_id}' does not match artifact-id '{aid}'",
                loc,
            )
        )


def check_artifact_type(
    fm: dict,
    valid: frozenset[str],
    label: str,
    result: VerificationResult,
    loc: str,
) -> None:
    if "artifact-type" not in fm:
        return
    artifact_type = str(fm["artifact-type"])
    if artifact_type not in valid:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E102",
                f"artifact-type '{artifact_type}' is not a recognised {label}",
                loc,
            )
        )


def check_enum(
    fm: dict,
    field_name: str,
    valid: frozenset[str],
    result: VerificationResult,
    loc: str,
) -> None:
    if field_name not in fm or fm[field_name] is None:
        return
    value = str(fm[field_name])
    if value not in valid:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E022",
                (f"Field '{field_name}' has invalid value '{value}'; expected one of: {sorted(valid)}"),
                loc,
            )
        )


def check_section(
    content: str,
    section: str,
    *,
    required: bool,
    result: VerificationResult,
    loc: str,
) -> None:
    marker = f"<!-- {section} -->"
    if marker in content:
        return
    severity = Severity.ERROR if required else Severity.WARNING
    code = "E031" if required else "W031"
    msg = f"Section marker '{marker}' is {'absent' if required else 'absent (optional for connections)'}"
    result.issues.append(Issue(severity, code, msg, loc))


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
        elif diagram_is_baselined and registry.entity_status(eid_str) == "draft":
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
        elif diagram_is_baselined and registry.connection_status(cid_str) == "draft":
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


def check_puml_structure(content: str, fm: dict, result: VerificationResult, loc: str) -> None:
    if "@startuml" not in content:
        result.issues.append(Issue(Severity.ERROR, "E304", "@startuml marker is missing", loc))
    if "@enduml" not in content:
        result.issues.append(Issue(Severity.ERROR, "E305", "@enduml marker is missing", loc))

    body_lines = [line for line in content.splitlines() if not line.lstrip().startswith("'")]
    has_visible_title = any(re.match(r"^\s*title(\s|$)", line, flags=re.IGNORECASE) for line in body_lines)
    if not has_visible_title:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E308",
                "Diagram must include a visible title line (for example: 'title <diagram name>')",
                loc,
            )
        )

    diagram_type = str(fm.get("diagram-type", ""))
    if "archimate" in diagram_type or "usecase" in diagram_type:
        has_stereotypes = "_archimate-stereotypes.puml" in content
        has_inlined_archimate = (
            "skinparam rectangle<<" in content and "hide stereotype" in content
        ) or "sprite $archimate_" in content
        has_inline_declarations = bool(
            re.search(r'rectangle\s+"[^"]*"\s+<<\w+>>', content)
        )
        if not has_stereotypes and not has_inlined_archimate and not has_inline_declarations:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E303",
                    (
                        "ArchiMate/use-case diagram must include "
                        "_archimate-stereotypes.puml or use inline ArchiMate element declarations"
                    ),
                    loc,
                )
            )

    _check_entity_aliases_declared(content, fm, result, loc)


def _check_entity_aliases_declared(content: str, fm: dict, result: VerificationResult, loc: str) -> None:
    entity_ids = fm.get("entity-ids-used")
    if not isinstance(entity_ids, list):
        return

    declared_aliases = _extract_declared_puml_aliases(content)
    for eid in entity_ids:
        eid_str = str(eid)
        matches = list((result.path.parents[2] / MODEL).rglob(f"{eid_str}.md"))
        if matches:
            try:
                entity_text = matches[0].read_text(encoding="utf-8")
            except OSError:
                entity_text = None
            if entity_text is not None:
                alias = _extract_entity_display_alias(entity_text)
                if alias and _normalize_puml_alias(alias) not in declared_aliases:
                    result.issues.append(
                        Issue(
                            Severity.ERROR,
                            "E309",
                            (
                                f"entity-ids-used references '{eid_str}' with display alias '{alias}', "
                                "but that alias is not declared in the PUML body"
                            ),
                            loc,
                        )
                    )


def _extract_declared_puml_aliases(content: str) -> set[str]:
    return _extract_declared_puml_aliases_shared(content)


def check_diagram_artifact_type(fm: dict, result: VerificationResult, loc: str) -> None:
    check_artifact_type(fm, DIAGRAM_ARTIFACT_TYPES, "diagram artifact type", result, loc)


def check_matrix_markdown_shape(fm: dict, content: str, result: VerificationResult, loc: str) -> None:
    """W321 (should declare diagram-type: matrix) and W322 (no table markup found)."""
    if "diagram-type" in fm and str(fm.get("diagram-type")) != "matrix":
        result.issues.append(Issue(
            Severity.WARNING, "W321",
            "Markdown diagram file under diagram-catalog/diagrams should use diagram-type: matrix", loc,
        ))
    if "|" not in content:
        result.issues.append(Issue(
            Severity.WARNING, "W322",
            "Matrix diagram markdown has no table markup; expected at least one matrix table", loc,
        ))
