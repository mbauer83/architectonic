"""Type catalog for model authoring tools.

Progressive discovery pattern:
  1. Call artifact_help to learn what artifact types, entity types,
     connection types, and diagram types exist.
  2. Call artifact_authoring_guidance(filter=...) for detailed entity type
     guidance before creating entities or connections.
  3. Call artifact_authoring_guidance(diagram_type=...) for authoring guidance
     on a specific diagram type before creating a diagram.
"""

from functools import lru_cache

from src.domain.modules.module_types import ElementClassName
from src.infrastructure.write.artifact_write.viewpoint_help_topic import viewpoints_help_topic


@lru_cache(maxsize=1)
def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


@lru_cache(maxsize=1)
def _archimate_stereotype_keys() -> tuple[str, ...]:
    from src.infrastructure.app_bootstrap import build_runtime_catalogs  # noqa: PLC0415

    return tuple(build_runtime_catalogs(_registry()).ontology.archimate_stereotype_to_connection_type())


def write_help() -> dict[str, object]:
    """Return the full type catalog grouped for quick scanning.

    Includes entity types (by domain), connection types (by language),
    diagram types (with accepted domains), ArchiMate stereotypes, and
    authoring conventions. For detailed per-type or per-diagram-type guidance
    call artifact_authoring_guidance.
    """
    return {
        "artifact_types": ["entity", "diagram", "document", "matrix"],
        "entity_types_by_domain": _entity_types_by_domain(),
        "entity_type_catalog": _entity_type_catalog(),
        "connection_types_by_language": _connection_types_by_language(),
        "connection_type_catalog": _connection_type_catalog(),
        "diagram_types": _diagram_types_catalog(),
        "archimate_stereotypes": sorted(_archimate_stereotype_keys()),
        "viewpoints": viewpoints_help_topic(),
        "conventions": {
            "entity_id_format": "TYPE@epoch.random.friendly-name (auto-generated)",
            "puml_alias_format": "TYPE_random (e.g. DRV_Qw7Er1)",
            "statuses": ["draft", "active", "deprecated"],
            "dry_run": "All create/edit tools default to dry_run=true for safe preview",
            "connection_inference": {
                "none": "No connections inferred from PUML. Only explicitly linked connections are recorded.",
                "auto": (
                    "Connections inferred from <<stereotype>> arrows in PUML. Unknown stereotypes produce warnings."
                ),
                "strict": "Connections inferred from <<stereotype>> arrows. Unknown stereotypes raise an error.",
            },
        },
        "next_steps": (
            "Call artifact_authoring_guidance(filter=[...]) for entity type authoring guidance. "
            "Call artifact_authoring_guidance(diagram_type='...') for diagram type authoring guidance."
        ),
    }


def _entity_types_by_domain() -> dict[str, list[str]]:
    internal = _registry().entity_types_with_class(ElementClassName("internal"))
    grouped: dict[str, list[str]] = {}
    for type_name, info in _registry().all_entity_types().items():
        if type_name in internal:
            continue
        domain = info.hierarchy[0] if info.hierarchy else "common"
        grouped.setdefault(domain, []).append(str(type_name))
    return grouped


def _entity_type_catalog() -> dict[str, dict[str, object]]:
    return {
        str(type_name): {
            "prefix": info.prefix,
            "hierarchy": list(info.hierarchy),
            "classes": list(info.classes),
        }
        for type_name, info in _registry().all_entity_types().items()
    }


def _connection_types_by_language() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for type_name, info in _registry().all_connection_types().items():
        lang = info.conn_lang
        grouped.setdefault(lang, []).append(str(type_name))
    return grouped


def _connection_type_catalog() -> dict[str, dict[str, object]]:
    return {
        str(type_name): {
            "language": info.conn_lang,
            "archimate_relationship_type": info.archimate_relationship_type,
            "symmetric": info.symmetric,
            "puml_arrow": info.puml_arrow,
        }
        for type_name, info in _registry().all_connection_types().items()
    }


def _diagram_types_catalog() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for kind in _registry().all_diagram_types().values():
        guidance = kind.write_guidance()
        entries.append(
            {
                "name": str(kind.name),
                "label": kind.ui_config.label,
                "accepted_domains": list(guidance.accepted_domains),
            }
        )
    return entries
