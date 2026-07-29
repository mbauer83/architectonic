"""Parsing for viewpoint definitions: the ``viewpoints: [ {slug, version, ...} ]`` YAML
shape (module-shipped starter library and ``.arch-repo/viewpoints.yaml``), Appendix-A
canonical form.

Enforces structural correctness only — known enum values, the ``query_schema`` version tag,
and unknown-key rejection — raising ``ValueError`` immediately for a malformed declaration.
Registry-aware correctness (unknown types/specializations/attributes) is a separate, later
concern — see ``viewpoint_validation.py``. Query/presentation leaf shapes live in
``viewpoint_query_parsing.py``/``viewpoint_presentation_parsing.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from src.domain.concept_scope import ConceptScope, HierarchyPredicate
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.viewpoints.viewpoint_presentation_parsing import presentation_from_mapping
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoints import (
    VALID_CONTENTS,
    VALID_PURPOSES,
    Content,
    ForkLineage,
    Purpose,
    ViewpointCatalog,
    ViewpointDefinition,
)

_DEFINITION_KEYS = frozenset(
    {
        "slug",
        "version",
        "name",
        "description",
        "rationale",
        "purpose",
        "content",
        "stakeholders",
        "concerns",
        "scope",
        "representation_types",
        "derivation_defaults",
        "query",
        "presentation",
        "selection_mode",
        "forked_from",
    }
)


def _check_keys(raw: Mapping[str, object], allowed: frozenset[str], *, label: str) -> None:
    unknown = set(raw.keys()) - allowed
    if unknown:
        raise ValueError(f"{label}: unknown key(s) {sorted(unknown)}")


def _require_purpose(value: object, *, label: str) -> Purpose:
    text = str(value)
    if text not in ("designing", "deciding", "informing"):
        raise ValueError(f"{label}: purpose {text!r} is not one of {sorted(VALID_PURPOSES)}")
    return text


def _require_content(value: object, *, label: str) -> Content:
    text = str(value)
    if text not in ("details", "coherence", "overview"):
        raise ValueError(f"{label}: content {text!r} is not one of {sorted(VALID_CONTENTS)}")
    return text


def _purpose_tuple(raw: object, *, label: str) -> tuple[Purpose, ...]:
    if raw is None:
        return ("informing",)
    if isinstance(raw, str):
        return (_require_purpose(raw, label=label),)
    if isinstance(raw, (list, tuple)):
        return tuple(_require_purpose(v, label=label) for v in raw)
    raise ValueError(f"{label}: purpose must be a string or list of strings")


def _content_tuple(raw: object, *, label: str) -> tuple[Content, ...]:
    if raw is None:
        return ("overview",)
    if isinstance(raw, str):
        return (_require_content(raw, label=label),)
    if isinstance(raw, (list, tuple)):
        return tuple(_require_content(v, label=label) for v in raw)
    raise ValueError(f"{label}: content must be a string or list of strings")


def _string_tuple(raw: object) -> tuple[str, ...]:
    return tuple(str(v) for v in raw) if isinstance(raw, (list, tuple)) else ()


def _string_frozenset(raw: object) -> frozenset[str]:
    return frozenset(str(v) for v in raw) if isinstance(raw, (list, tuple)) else frozenset()


def _fork_lineage_from_mapping(raw: object, *, label: str) -> ForkLineage | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label}: forked_from must be a mapping")
    unknown = set(raw.keys()) - {"slug", "version", "definition_digest", "index_generation"}
    if unknown:
        raise ValueError(f"{label}: forked_from: unknown key(s) {sorted(unknown)}")
    slug = raw.get("slug")
    digest = raw.get("definition_digest")
    if not isinstance(slug, str) or not slug or not isinstance(digest, str) or not digest:
        raise ValueError(f"{label}: forked_from requires 'slug' and 'definition_digest'")
    generation = raw.get("index_generation")
    return ForkLineage(
        slug=slug,
        version=int(raw.get("version", 1)),
        definition_digest=digest,
        index_generation=int(generation) if isinstance(generation, int) else None,
    )


def _selection_mode(raw: object, *, label: str) -> Literal["scope", "query"] | None:
    if raw is None:
        return None
    if raw not in ("scope", "query"):
        raise ValueError(f"{label}: selection_mode must be 'scope' or 'query'")
    return cast(Literal["scope", "query"], raw)


_SCOPE_KEYS = frozenset(
    {"entity_types", "connection_types", "excluded_entity_types", "excluded_domains", "excluded_connection_types"}
)


def _scope_from_mapping(raw: object) -> ConceptScope:
    if not isinstance(raw, Mapping):
        return ConceptScope.unrestricted()
    _check_keys(raw, _SCOPE_KEYS, label="scope")
    entity_types = raw.get("entity_types")
    connection_types = raw.get("connection_types")
    excluded_domains = _string_frozenset(raw.get("excluded_domains"))
    return ConceptScope(
        entity_types=(
            frozenset(EntityTypeName(t) for t in _string_frozenset(entity_types)) if entity_types is not None else None
        ),
        connection_types=(
            frozenset(ConnectionTypeName(t) for t in _string_frozenset(connection_types))
            if connection_types is not None
            else None
        ),
        excluded_entity_types=frozenset(EntityTypeName(t) for t in _string_frozenset(raw.get("excluded_entity_types"))),
        excluded_hierarchy_predicates=(
            (HierarchyPredicate(index=0, values=excluded_domains),) if excluded_domains else ()
        ),
        excluded_connection_types=frozenset(
            ConnectionTypeName(t) for t in _string_frozenset(raw.get("excluded_connection_types"))
        ),
    )


def viewpoint_definition_from_mapping(raw: Mapping[str, Any]) -> ViewpointDefinition:
    slug = str(raw["slug"])
    label = f"viewpoint '{slug}'"
    _check_keys(raw, _DEFINITION_KEYS, label=label)
    derivation_defaults = raw.get("derivation_defaults")
    return ViewpointDefinition(
        slug=slug,
        version=int(raw.get("version", 1)),
        name=str(raw.get("name") or slug.replace("-", " ").title()),
        description=str(raw.get("description") or ""),
        rationale=str(raw.get("rationale") or ""),
        purpose=_purpose_tuple(raw.get("purpose"), label=label),
        content=_content_tuple(raw.get("content"), label=label),
        stakeholders=_string_tuple(raw.get("stakeholders")),
        concerns=_string_tuple(raw.get("concerns")),
        scope=_scope_from_mapping(raw.get("scope")),
        representation_types=_string_tuple(raw.get("representation_types")),
        derivation_defaults=dict(derivation_defaults) if isinstance(derivation_defaults, Mapping) else {},
        query=query_from_mapping(raw.get("query"), label=label) if raw.get("query") is not None else None,
        presentation=presentation_from_mapping(raw.get("presentation"), label=label),
        selection_mode=_selection_mode(raw.get("selection_mode"), label=label),
        forked_from=_fork_lineage_from_mapping(raw.get("forked_from"), label=label),
    )


def viewpoint_definitions_from_mapping(data: Mapping[str, Any]) -> tuple[ViewpointDefinition, ...]:
    """Parse the ``viewpoints: [ {slug, version, ...} ]`` YAML shape."""
    raw_entries = data.get("viewpoints")
    if not isinstance(raw_entries, (list, tuple)):
        return ()
    return tuple(viewpoint_definition_from_mapping(raw) for raw in raw_entries if isinstance(raw, Mapping))


def viewpoint_catalog_from_mapping(data: Mapping[str, Any]) -> ViewpointCatalog:
    """Parse viewpoint definitions and return a validating catalog (slug-unique)."""
    return ViewpointCatalog(viewpoint_definitions_from_mapping(data))
