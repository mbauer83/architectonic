"""GroupRegistry loader — reads .arch-repo/groups.yaml and validates against the bundled schema.

Tolerant of missing file or missing sections: synthesises ``uncategorized`` (and an
engagement-named model-project default when engagement_label is supplied) so callers
always receive a fully populated registry.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.domain.clock import epoch_seconds
from src.domain.repository.groups import UNCATEGORIZED, GroupAxis, GroupEntry, GroupRegistry
from src.domain.repository.repo_layout import ARCH_REPO
from src.domain.yaml_documents import parse_yaml

_GROUPS_FILE = "groups.yaml"

# JSON Schema bundled in source — each repo's .arch-repo/schemata/ may also hold a copy
# for human reference, but validation uses this authoritative definition.
_BASE_ENTRY_PROPS: dict[str, object] = {
    "slug": {"type": "string", "minLength": 1},
    "id": {"type": "string", "minLength": 1},
    "name": {"type": "string", "minLength": 1},
    "description": {"type": "string"},
    "order": {"type": "integer"},
    "archived": {"type": "boolean"},
    "default": {"type": "boolean"},
}

_GROUPS_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "groups.schema.json",
    "title": "Groups Registry Schema",
    "description": "Schema for .arch-repo/groups.yaml — one section per grouping axis.",
    "type": "object",
    "properties": {
        "model-projects": {"type": "array", "items": {"$ref": "#/$defs/model_project_entry"}},
        "diagram-collections": {"type": "array", "items": {"$ref": "#/$defs/collection_entry"}},
        "document-collections": {"type": "array", "items": {"$ref": "#/$defs/collection_entry"}},
        "analysis-collections": {"type": "array", "items": {"$ref": "#/$defs/collection_entry"}},
    },
    "additionalProperties": False,
    "$defs": {
        "model_project_entry": {
            "type": "object",
            "required": ["slug", "id", "name"],
            "properties": {**_BASE_ENTRY_PROPS, "meta_ontology": {"type": "string"}},
            "additionalProperties": False,
        },
        "collection_entry": {
            "type": "object",
            "required": ["slug", "id", "name"],
            "properties": {
                **_BASE_ENTRY_PROPS,
                "type_filter": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    },
}

_AXIS_KEYS: dict[GroupAxis, str] = {
    "model-project": "model-projects",
    "diagram-collection": "diagram-collections",
    "document-collection": "document-collections",
    "analysis-collection": "analysis-collections",
}


def _to_int(val: object, default: int) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return default


def _new_group_id() -> str:
    """Allocate a fresh opaque group id (uses epoch ms + random suffix)."""
    import random
    import string

    epoch = epoch_seconds()
    rand = "".join(random.choices(string.ascii_letters + string.digits, k=6))
    return f"GRP@{epoch}.{rand}"


def _uncategorized_entry() -> GroupEntry:
    return GroupEntry(slug=UNCATEGORIZED, id=f"GRP@0.{UNCATEGORIZED}", name="Uncategorized")


def _parse_entries(raw: list[dict[str, object]], axis: GroupAxis) -> list[GroupEntry]:
    is_model = axis == "model-project"
    entries: list[GroupEntry] = []
    for item in raw:
        tf_raw = item.get("type_filter", [])
        entries.append(
            GroupEntry(
                slug=str(item["slug"]),
                id=str(item["id"]),
                name=str(item["name"]),
                description=str(item.get("description") or ""),
                order=_to_int(item.get("order"), 0),
                archived=bool(item.get("archived", False)),
                default=bool(item.get("default", False)),
                meta_ontology=str(item.get("meta_ontology") or "") if is_model else "",
                type_filter=tuple(str(t) for t in tf_raw) if isinstance(tf_raw, list) and not is_model else (),
            )
        )
    if not any(e.slug == UNCATEGORIZED for e in entries):
        entries.append(_uncategorized_entry())
    return entries


def _validate(data: dict[str, object]) -> None:
    try:
        import jsonschema

        jsonschema.validate(data, _GROUPS_SCHEMA)
    except ImportError:
        pass  # jsonschema unavailable — skip; startup_validation covers this


def load_group_registry(repo_root: Path, *, engagement_label: str = "") -> GroupRegistry:
    """Load and return the GroupRegistry for repo_root.

    Falls back to synthesised defaults when groups.yaml is absent or a section is missing.
    """
    groups_path = repo_root / ARCH_REPO / _GROUPS_FILE

    raw: dict[str, object] = {}
    if groups_path.exists():
        text = groups_path.read_text(encoding="utf-8")
        loaded = parse_yaml(text)
        if isinstance(loaded, dict):
            raw = loaded
            _validate(raw)

    def _axis(key: str) -> list[dict[str, object]]:
        val = raw.get(key, [])
        return val if isinstance(val, list) else []

    mp_raw = _axis("model-projects")
    dc_raw = _axis("diagram-collections")
    dcc_raw = _axis("document-collections")
    ac_raw = _axis("analysis-collections")

    model_projects = _parse_entries(mp_raw, "model-project")
    diagram_collections = _parse_entries(dc_raw, "diagram-collection")
    document_collections = _parse_entries(dcc_raw, "document-collection")
    analysis_collections = _parse_entries(ac_raw, "analysis-collection")

    # When no explicit default is set and an engagement label exists, synthesise one
    if engagement_label and not any(e.default for e in model_projects):
        slug = _slug_from_label(engagement_label)
        existing = next((e for e in model_projects if e.slug == slug), None)
        if existing is None:
            model_projects.append(
                GroupEntry(
                    slug=slug,
                    id=_new_group_id(),
                    name=engagement_label.replace("-", " ").title(),
                    default=True,
                )
            )
        else:
            # Promote existing entry to default
            model_projects = [
                GroupEntry(
                    slug=e.slug,
                    id=e.id,
                    name=e.name,
                    description=e.description,
                    order=e.order,
                    archived=e.archived,
                    default=True,
                )
                if e.slug == slug
                else e
                for e in model_projects
            ]

    return GroupRegistry(
        model_projects=tuple(model_projects),
        diagram_collections=tuple(diagram_collections),
        document_collections=tuple(document_collections),
        analysis_collections=tuple(analysis_collections),
    )


def _slug_from_label(label: str) -> str:
    """Convert an engagement label to a valid directory slug."""
    return label.lower().replace("_", "-").replace(" ", "-")


def registry_to_yaml(registry: GroupRegistry) -> str:
    """Serialise a GroupRegistry back to the groups.yaml format."""

    def _entries_to_list(entries: tuple[GroupEntry, ...]) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for e in entries:
            if e.slug == UNCATEGORIZED and e.id == f"GRP@0.{UNCATEGORIZED}":
                continue  # synthetic sentinel injected at load time; never persisted
            d: dict[str, object] = {"slug": e.slug, "id": e.id, "name": e.name}
            if e.description:
                d["description"] = e.description
            if e.order:
                d["order"] = e.order
            if e.archived:
                d["archived"] = True
            if e.default:
                d["default"] = True
            if e.meta_ontology:
                d["meta_ontology"] = e.meta_ontology
            if e.type_filter:
                d["type_filter"] = list(e.type_filter)
            result.append(d)
        return result

    data: dict[str, object] = {}
    if registry.model_projects:
        data["model-projects"] = _entries_to_list(registry.model_projects)
    if registry.diagram_collections:
        data["diagram-collections"] = _entries_to_list(registry.diagram_collections)
    if registry.document_collections:
        data["document-collections"] = _entries_to_list(registry.document_collections)
    if registry.analysis_collections:
        data["analysis-collections"] = _entries_to_list(registry.analysis_collections)

    result = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return result if isinstance(result, str) else ""


def write_groups_schema(repo_root: Path) -> None:
    """Write the bundled groups.schema.json into repo_root/.arch-repo/schemata/."""
    schemata_dir = repo_root / ARCH_REPO / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    schema_path = schemata_dir / "groups.schema.json"
    schema_path.write_text(json.dumps(_GROUPS_SCHEMA, indent=2), encoding="utf-8")
