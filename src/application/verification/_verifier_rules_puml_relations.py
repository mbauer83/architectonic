"""Rule: verify that PUML relation declarations reference valid model connections.

Relations are read through the ONE shared parser (``src.application.puml_relation_parsing``).
This file used to carry its own blind regex copy that recognised only macro calls and
stereotype-labelled arrows — the forms the renderer never emits — so the rule failed open on
every generated body. Copies of a parser drift; this one had drifted into seeing nothing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from src.application.puml_relation_parsing import declared_relations
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.artifact_id import stable_conn_id as _stable_conn_id

_STD_ALIAS_RE = re.compile(r"^(?P<prefix>[A-Z]{2,6})_(?P<random>[A-Za-z0-9_-]{4,})$")


def _normalize_puml_alias(alias: str) -> str:
    return alias.strip().replace("-", "_")


def _normalize_standard_alias(artifact_id: str) -> str:
    parts = artifact_id.split(".")
    if len(parts) < 2 or "@" not in parts[0]:
        return ""
    prefix = parts[0].split("@", 1)[0]
    return f"{prefix}_{parts[1]}"


def _resolve_standard_alias(alias: str, entity_ids: set[str]) -> str | None:
    match = _STD_ALIAS_RE.match(alias)
    if match is None:
        return None
    prefix = match.group("prefix")
    random = match.group("random")
    needle = f".{random}."
    for entity_id in entity_ids:
        if entity_id.startswith(f"{prefix}@") and needle in entity_id:
            return entity_id
    return None


def _extract_entity_display_alias(entity_text: str) -> str:
    marker = "<!-- §display -->"
    pos = entity_text.find(marker)
    if pos == -1:
        return ""
    display_body = entity_text[pos + len(marker):]
    m = re.search(r"alias:\s*([A-Za-z0-9_-]+)", display_body)
    return _normalize_puml_alias(m.group(1)) if m else ""


def _iter_typed_relations(
    content: str, stereotype_map: Mapping[str, str]
) -> list[tuple[str, str, str]]:
    """Every relation the body states WITH a type, via the shared parser.

    Bare arrows and containment nesting carry no type and cannot be existence-checked against
    a specific connection; their completeness is the concern of
    ``_verifier_rules_puml_completeness``.
    """
    return [
        (relation.source_alias, relation.target_alias, relation.connection_type)
        for relation in declared_relations(content, stereotype_map)
        if relation.connection_type is not None
    ]


def _build_alias_lookup(
    content: str, fm: dict, registry: ArtifactRegistry, stereotype_map: Mapping[str, str]
) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    display_alias_to_entity_id: dict[str, str] = {}

    for entity_id in registry.entity_ids():
        path = registry.find_file_by_id(entity_id)
        if path is None:
            continue
        try:
            entity_text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        alias = _extract_entity_display_alias(entity_text)
        if alias:
            display_alias_to_entity_id.setdefault(_normalize_puml_alias(alias), entity_id)

    for eid in fm.get("entity-ids-used", []) if isinstance(fm.get("entity-ids-used"), list) else []:
        eid_str = str(eid)
        std_alias = _normalize_standard_alias(eid_str)
        if std_alias:
            alias_map[std_alias] = eid_str
            alias_map[_normalize_puml_alias(std_alias)] = eid_str
        alias = display_alias_to_entity_id.get(_normalize_puml_alias(std_alias), "")
        if alias:
            alias_map[_normalize_puml_alias(std_alias)] = alias
        display_alias = ""
        path = registry.find_file_by_id(eid_str)
        if path is not None:
            try:
                entity_text = path.read_text(encoding="utf-8")
            except OSError:
                entity_text = ""
            display_alias = _extract_entity_display_alias(entity_text) if entity_text else ""
        if display_alias:
            alias_map[display_alias] = eid_str

    from src.application.artifact_parsing import (  # noqa: PLC0415
        extract_declared_puml_aliases as _extract_declared_puml_aliases,
    )

    aliases_to_resolve = set(_extract_declared_puml_aliases(content))
    for relation in declared_relations(content, stereotype_map):
        aliases_to_resolve.add(relation.source_alias)
        aliases_to_resolve.add(relation.target_alias)

    for alias in aliases_to_resolve:
        normalized = _normalize_puml_alias(alias)
        if alias in alias_map or normalized in alias_map:
            continue
        resolved = display_alias_to_entity_id.get(normalized)
        if resolved is not None:
            alias_map[alias] = resolved
            alias_map[normalized] = resolved
            continue
        resolved = _resolve_standard_alias(alias, registry.entity_ids())
        if resolved is None:
            resolved = _resolve_standard_alias(normalized, registry.entity_ids())
        if resolved is not None:
            alias_map[alias] = resolved
            alias_map[normalized] = resolved

    return alias_map


def check_diagram_relation_references(
    content: str,
    fm: dict,
    registry: ArtifactRegistry,
    file_scope: Literal["enterprise", "engagement", "unknown"],
    result: VerificationResult,
    loc: str,
    *,
    stereotype_map: Mapping[str, str],
) -> None:
    allowed_connections = (
        registry.enterprise_connection_ids() if file_scope == "enterprise" else registry.connection_ids()
    )
    all_connections = registry.connection_ids()
    allowed_stable = {_stable_conn_id(c) for c in allowed_connections}
    all_stable = {_stable_conn_id(c) for c in all_connections}
    alias_to_entity_id = _build_alias_lookup(content, fm, registry, stereotype_map)

    for src_alias, tgt_alias, conn_type in _iter_typed_relations(content, stereotype_map):
        src_id = alias_to_entity_id.get(src_alias) or alias_to_entity_id.get(_normalize_puml_alias(src_alias))
        tgt_id = alias_to_entity_id.get(tgt_alias) or alias_to_entity_id.get(_normalize_puml_alias(tgt_alias))
        if src_id is None:
            result.issues.append(
                Issue(Severity.ERROR, "E311", f"diagram relation references unknown source alias '{src_alias}'", loc)
            )
            continue
        if tgt_id is None:
            result.issues.append(
                Issue(Severity.ERROR, "E311", f"diagram relation references unknown target alias '{tgt_alias}'", loc)
            )
            continue

        stable_cid = _stable_conn_id(f"{src_id}---{tgt_id}@@{conn_type}")
        if stable_cid in allowed_stable:
            continue

        stable_rev = _stable_conn_id(f"{tgt_id}---{src_id}@@{conn_type}")
        if conn_type == "archimate-realization" and stable_rev in allowed_stable:
            continue

        if stable_cid in all_stable or stable_rev in all_stable:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E313",
                    f"diagram relation '{conn_type}' between '{src_alias}' and '{tgt_alias}' "
                    "is out of scope for this repository",
                    loc,
                )
            )
            continue

        result.issues.append(
            Issue(
                Severity.ERROR,
                "E312",
                f"diagram relation '{conn_type}' between '{src_alias}' and '{tgt_alias}' "
                "does not exist in the model",
                loc,
            )
        )
