from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.application.artifacts.schema import (
    load_attribute_schema,
    schema_all_properties,
    schema_required_properties,
)
from src.domain.ontology_representation.property_value import encode as _encode_cell
from src.domain.repository.connection_declaration import ConnectionDeclaration, format_connection_declaration


def _specialization_frontmatter_value(specializations: Sequence[str] | None) -> str | list[str] | None:
    """The value to write for the ``specialization`` frontmatter key, or ``None`` to omit it.

    A single specialization is written as a SCALAR — so existing one-specialization files
    stay byte-identical and no repo is churned — and several as a list (§15.2). Blanks and
    duplicates are dropped. The *key* keeps its singular name because 146 files use it; what
    varies is the value's shape, which `applied_specialization_slugs` reads back.
    """
    raw = list(specializations) if specializations else []
    seen: dict[str, None] = {}
    for item in raw:
        if item and item not in seen:
            seen[item] = None
    applied = list(seen)
    if not applied:
        return None
    return applied[0] if len(applied) == 1 else applied


def _as_str_list(value: object) -> list[str]:
    """A connection's ``specialization`` conn-dict value as a list, accepting a scalar
    (one element) or an already-list value."""
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


def _dump_yaml_text(data: object) -> str:
    dumped = yaml.safe_dump(data, sort_keys=False)
    if not isinstance(dumped, str):
        raise TypeError("yaml.safe_dump returned non-string output")
    return dumped.strip()


def format_entity_markdown(
    *,
    artifact_id: str,
    artifact_type: str,
    name: str,
    version: str,
    status: str,
    last_updated: str,
    keywords: list[str] | None = None,
    specializations: Sequence[str] | None = None,
    summary: str | None,
    properties: dict[str, Any] | None,
    attribute_types: dict[str, str] | None = None,
    notes: str | None,
    display_section_id: str,
    display_content: str,
    repo_root: Path | None = None,
    extra_frontmatter: dict[str, object] | None = None,
) -> str:
    """Format a complete entity markdown file.

    ``display_section_id`` and ``display_content`` are provided by the owning
    ontology module via ``render_display_section``.  The content is embedded
    under ``### {display_section_id}`` inside the ``<!-- §display -->`` block.
    """
    frontmatter: dict[str, object] = {
        "artifact-id": artifact_id,
        "artifact-type": artifact_type,
        "name": name,
        "version": version,
        "status": status,
    }
    if keywords:
        frontmatter["keywords"] = keywords
    applied = _specialization_frontmatter_value(specializations)
    if applied is not None:
        frontmatter["specialization"] = applied
    if attribute_types:
        frontmatter["attribute-types"] = attribute_types
    frontmatter["last-updated"] = last_updated

    ordered_keys = [
        "artifact-id",
        "artifact-type",
        "name",
        "version",
        "status",
        "keywords",
        "specialization",
        "attribute-types",
        "last-updated",
    ]
    fm_out = {key: frontmatter[key] for key in ordered_keys if key in frontmatter}
    if extra_frontmatter:
        fm_out.update(extra_frontmatter)

    content_lines: list[str] = ["<!-- §content -->", "", f"## {name}", ""]
    if summary:
        content_lines.append(summary.strip())
        content_lines.append("")

    content_lines.extend(["## Properties", "", "| Attribute | Value |", "|---|---|"])
    props = properties or {}
    scaffold_keys = _scaffold_keys_from_schema(repo_root, artifact_type)
    if props:
        for key in sorted(props.keys()):
            content_lines.append(f"| {key} | {_encode_cell(props[key])} |")
        for key in scaffold_keys:
            if key not in props:
                content_lines.append(f"| {key} | |")
    elif scaffold_keys:
        for key in scaffold_keys:
            content_lines.append(f"| {key} | |")
    else:
        content_lines.append("| (none) | (none) |")
    content_lines.append("")

    if notes and notes.strip():
        content_lines.extend(["## Notes", "", notes.strip(), ""])

    display_lines = [
        "<!-- §display -->",
        "",
        f"### {display_section_id}",
        "",
        "```yaml",
        display_content.strip(),
        "```",
    ]
    frontmatter_text = _dump_yaml_text(fm_out)
    return (
        "---\n" + frontmatter_text + "\n---\n\n" + "\n".join(content_lines) + "\n\n" + "\n".join(display_lines) + "\n"
    )


def format_outgoing_markdown(
    *,
    source_entity: str,
    version: str,
    status: str,
    last_updated: str,
    connections: list[dict[str, object]],
) -> str:
    """Format an .outgoing.md file.

    Each entry in *connections* should have keys:
      - ``connection_type``: e.g. ``archimate-realization``
      - ``target_entity``: target artifact-id
      - ``description``: prose description of the relationship (optional)
      - ``src_multiplicity``: source-end multiplicity (optional, e.g. "1", "0..1", "1..*", "*")
      - ``tgt_multiplicity``: target-end multiplicity (optional, same format)
      - ``specialization``: a specialization slug (optional) — persisted in the
        per-connection metadata block, never folded into ``description``
      - ``metadata``: the rest of the per-connection metadata block (optional), carried
        through verbatim so a reformat never drops schema-declared attributes

    Header format:  ### conn-type [src_mult] → [tgt_mult] target_id
    Both multiplicity parts are omitted when absent.  Multiplicities are not
    permitted on junction connections.
    """
    frontmatter = {
        "source-entity": source_entity,
        "version": version,
        "status": status,
        "last-updated": last_updated,
    }
    frontmatter_text = _dump_yaml_text(frontmatter)

    sections: list[str] = ["<!-- §connections -->"]
    for conn in connections:
        assoc_ids = conn.get("associated_entities")
        raw_metadata = conn.get("metadata")
        metadata: dict[str, Any] = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        # ``specialization`` is authoritative as its own key: the edit API sets and clears
        # it by name, so it overrides (or removes) whatever the carried block held. One is
        # written as a scalar (byte-identical to existing files), several as a list (§15.2).
        applied = _specialization_frontmatter_value(_as_str_list(conn.get("specialization")))
        if applied is not None:
            metadata["specialization"] = applied
        else:
            metadata.pop("specialization", None)
        decl = ConnectionDeclaration(
            conn_type=str(conn["connection_type"]),
            target_id=str(conn["target_entity"]),
            src_multiplicity=str(conn.get("src_multiplicity", "")).strip(),
            tgt_multiplicity=str(conn.get("tgt_multiplicity", "")).strip(),
            description=str(conn.get("description", "")).strip(),
            associated_entities=tuple(assoc_ids) if isinstance(assoc_ids, list) else (),
            metadata=metadata,
        )
        sections.append("")
        sections.append(format_connection_declaration(decl))

    return "---\n" + frontmatter_text + "\n---\n\n" + "\n".join(sections) + "\n"


def format_matrix_markdown(
    *,
    artifact_id: str,
    name: str,
    version: str,
    status: str,
    last_updated: str,
    keywords: list[str] | None = None,
    matrix_markdown: str,
    entity_ids: list[str] | None = None,
    from_entity_ids: list[str] | None = None,
    to_entity_ids: list[str] | None = None,
    conn_type_configs: list[dict[str, object]] | None = None,
    combined: bool | None = None,
) -> str:
    frontmatter: dict[str, object] = {
        "artifact-id": artifact_id,
        "artifact-type": "diagram",
        "diagram-type": "matrix",
        "name": name,
        "version": version,
        "status": status,
    }
    if keywords:
        frontmatter["keywords"] = keywords
    frontmatter["last-updated"] = last_updated
    # Either axis being stated writes both, so the pair stays a pair. Keyed on `from` alone, a
    # caller stating only the column axis got neither — the value was accepted and dropped, which
    # is the one answer worse than a refusal.
    if from_entity_ids is not None or to_entity_ids is not None:
        frontmatter["from-entity-ids"] = from_entity_ids or []
        frontmatter["to-entity-ids"] = to_entity_ids or []
    elif entity_ids:
        frontmatter["entity-ids"] = entity_ids
    if conn_type_configs:
        frontmatter["conn-type-configs"] = conn_type_configs
    if combined is not None:
        frontmatter["combined"] = combined

    ordered_keys = [
        "artifact-id",
        "artifact-type",
        "diagram-type",
        "name",
        "version",
        "status",
        "keywords",
        "last-updated",
        "entity-ids",
        "from-entity-ids",
        "to-entity-ids",
        "conn-type-configs",
        "combined",
    ]
    fm_out = {key: frontmatter[key] for key in ordered_keys if key in frontmatter}
    yaml_text = _dump_yaml_text(fm_out)
    body = matrix_markdown.strip("\n") + "\n"
    return f"---\n{yaml_text}\n---\n\n{body}"


def _scaffold_keys_from_schema(repo_root: Path | None, artifact_type: str) -> list[str]:
    """Return ordered attribute keys from the attribute schema for scaffolding."""
    if repo_root is None:
        return []
    schema = load_attribute_schema(repo_root, artifact_type)
    if schema is None:
        return []
    required = schema_required_properties(schema)
    all_props = schema_all_properties(schema)
    optional = [key for key in all_props if key not in required]
    return required + optional
