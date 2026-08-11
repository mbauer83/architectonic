import re
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.application.verification.artifact_verifier_types import entity_id_from_path
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import (
    STANDARD_DIAGRAM_FIELDS,
    STANDARD_DOCUMENT_FIELDS,
    STANDARD_ENTITY_FIELDS,
    STANDARD_OUTGOING_FIELDS,
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    Domain,
    EntityRecord,
)
from src.domain.ontology_representation.property_value import decode_lenient, get_adhoc_type
from src.domain.ontology_representation.specialization_values import applied_specialization_slugs
from src.domain.repository.connection_declaration import parse_connection_declarations
from src.domain.repository.frontmatter import Frontmatter, body_after_frontmatter, read_frontmatter
from src.domain.yaml_documents import parse_yaml


def extract_yaml_block(content: str) -> dict | None:
    """The frontmatter mapping, or None when there is no readable block.

    `None` and `{}` mean different things to callers here and must stay apart: the
    unrecognized-structure upgrade step reports "starts with `---` but the block is malformed or
    unterminated" on `None`, and falls through to its artifact-type checks on `{}`. So this reads
    `read_frontmatter` rather than `parse_frontmatter`, which answers `{}` for both.
    """
    reading = read_frontmatter(content)
    if not isinstance(reading, Frontmatter):
        return None
    try:
        parsed = parse_yaml(reading.text)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else {}


def extract_section(content: str, marker: str) -> str:
    start_tag = f"<!-- §{marker} -->"
    start = content.find(start_tag)
    if start == -1:
        return ""
    body_start = start + len(start_tag)
    next_tag = re.search(r"<!-- §\w+ -->", content[body_start:])
    if next_tag:
        return content[body_start : body_start + next_tag.start()].strip()
    return content[body_start:].strip()


def extract_display_blocks(content: str) -> dict[str, str]:
    display_body = extract_section(content, "display")
    if not display_body:
        return {}

    blocks: dict[str, str] = {}
    parts = re.split(r"^###\s+(.+)$", display_body, flags=re.MULTILINE)
    iterator = iter(parts[1:])
    for lang, body in zip(iterator, iterator):
        blocks[lang.strip()] = body.strip()
    return blocks


def decode_entity_properties(
    raw_props: dict[str, str],
    prop_schemata: dict[str, dict],
    attribute_types: dict[str, str],
) -> dict[str, Any]:
    """Decode raw Markdown-cell property strings to typed Python values.

    *raw_props* is a ``{attr_name: cell_string}`` dict (from
    ``_extract_properties_map``).  *prop_schemata* is the ``properties`` dict
    from the entity's JSON-Schema attribute schema.  *attribute_types* is the
    ``attribute-types`` frontmatter map used for ad-hoc (non-schema) attributes.

    Decode failures produce a ``str`` fallback (raw cell) — never raises.
    """
    decoded: dict[str, Any] = {}
    for key, cell in raw_props.items():
        prop_schema = prop_schemata.get(key)
        if prop_schema:
            value, _ = decode_lenient(cell, prop_schema)
        else:
            adhoc_type = get_adhoc_type(key, attribute_types)
            value, _ = decode_lenient(cell, {"type": adhoc_type})
        decoded[key] = value
    return decoded


def parse_entity_content_sections(content_section: str) -> dict[str, Any]:
    """Extract summary, properties, and notes from an entity content section."""

    def _extract_summary_text(text: str) -> str:
        lines = text.strip().splitlines()
        collecting = False
        summary_lines: list[str] = []

        for line in lines:
            if line.startswith("## ") and not collecting:
                collecting = True
                continue
            if collecting:
                if line.startswith("## "):
                    break
                summary_lines.append(line)
        return "\n".join(summary_lines).strip()

    def _extract_properties_map(text: str) -> dict[str, str]:
        props: dict[str, str] = {}
        in_table = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "## Properties":
                in_table = True
                continue
            if in_table and stripped.startswith("## "):
                break
            if in_table and stripped.startswith("|") and "---" not in stripped:
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                if len(cells) >= 2 and cells[0] not in ("Attribute", "(none)"):
                    props[cells[0]] = cells[1]
        return props

    def _extract_notes_text(text: str) -> str:
        lines = text.splitlines()
        in_notes = False
        notes_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped == "## Notes":
                in_notes = True
                continue
            if in_notes:
                if stripped.startswith("## "):
                    break
                notes_lines.append(line)
        return "\n".join(notes_lines).strip()

    return {
        "summary": _extract_summary_text(content_section),
        "properties": _extract_properties_map(content_section),
        "notes": _extract_notes_text(content_section),
    }


def parse_diagram_source(content: str) -> dict[str, Any]:
    """Extract frontmatter and body from diagram source text."""
    frontmatter = extract_yaml_block(content) or {}
    body = body_after_frontmatter(content)
    return {"frontmatter": frontmatter, "puml_body": body}


def derive_domain(
    path: Path, root: Path, *, domain_names: frozenset[str]
) -> tuple[Domain, str]:
    try:
        rel = path.relative_to(root)
        parts = rel.parts
        domain_raw = parts[0] if len(parts) > 0 else "unknown"
        subdomain = parts[1] if len(parts) > 1 else ""
        domain: Domain = domain_raw if domain_raw in domain_names else "unknown"  # type: ignore[assignment]
        return domain, subdomain
    except ValueError:
        return "unknown", ""


def extract_archimate_label_alias(display_blocks: Mapping[str, str]) -> tuple[str, str]:
    archimate_block = display_blocks.get("archimate", "")
    if not archimate_block:
        return "", ""
    block = re.sub(r"```\w*\s*|\s*```", " ", archimate_block)
    label_match = re.search(r"label:\s*[\"']?([^\"'\n]+)[\"']?", block)
    alias_match = re.search(r"alias:\s*([A-Za-z0-9_-]+)", block)
    label = label_match.group(1).strip() if label_match else ""
    alias = alias_match.group(1).strip().replace("-", "_") if alias_match else ""
    return label, alias


def normalize_puml_alias(alias: str) -> str:
    return alias.strip().replace("-", "_")


_PUML_MACRO_ALIAS_RE = re.compile(r"^[A-Z][A-Za-z_]*\(\s*([A-Za-z0-9_]+)\s*,")


def extract_declared_puml_aliases(content: str) -> set[str]:
    aliases: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("'"):
            continue
        m = re.search(r"\bas\s+([A-Za-z0-9_-]+)\s*\{?\s*$", stripped)
        if m:
            aliases.add(normalize_puml_alias(m.group(1)))
            continue
        # Some PUML renderers emit macro calls where the alias is the first argument:
        # MacroName(ALIAS, "label", ...) rather than `element ... as ALIAS`.
        m2 = _PUML_MACRO_ALIAS_RE.match(stripped)
        if m2:
            aliases.add(normalize_puml_alias(m2.group(1)))
    return aliases


def _canonical_stamp(value: object) -> str | None:
    """Normalize a frontmatter `last-updated` scalar to one stable lexical string.

    PyYAML parses an *unquoted* ISO scalar into a `datetime`/`date` object; `str()` on a
    tz-aware datetime yields `2026-07-24 09:15:00+00:00` (space, `+00:00`), which drifts from
    the tool-written canonical `2026-07-24T09:15:00Z`. Normalize objects back to canonical form
    so comparison/sort see one shape; pass strings through; treat empty/None as absent.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def parse_entity(
    path: Path, model_root: Path, *, domain_names: frozenset[str]
) -> EntityRecord | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    frontmatter = extract_yaml_block(content)
    if not frontmatter:
        return None

    domain, subdomain = derive_domain(path, model_root, domain_names=domain_names)
    display_blocks = extract_display_blocks(content)
    display_label, display_alias = extract_archimate_label_alias(display_blocks)

    kw_raw: object = frontmatter.get("keywords") or []
    keywords: tuple[str, ...] = tuple(str(k) for k in kw_raw) if isinstance(kw_raw, list) else ()

    specializations = applied_specialization_slugs(frontmatter.get("specialization"))

    content_text = extract_section(content, "content")
    return EntityRecord(
        artifact_id=str(frontmatter.get("artifact-id", entity_id_from_path(path))),
        artifact_type=str(frontmatter.get("artifact-type", "")),
        name=str(frontmatter.get("name", "")),
        version=str(frontmatter.get("version", "")),
        status=str(frontmatter.get("status", "draft")),
        domain=domain,
        subdomain=subdomain,
        keywords=keywords,
        specializations=specializations,
        path=path,
        extra={key: value for key, value in frontmatter.items() if key not in STANDARD_ENTITY_FIELDS},
        content_text=content_text,
        display_blocks=display_blocks,
        display_label=display_label,
        display_alias=display_alias,
        attributes=_decode_attributes(content_text, frontmatter),
        last_updated=_canonical_stamp(frontmatter.get("last-updated")),
    )


def _decode_attributes(content_text: str, frontmatter: dict) -> dict[str, Any]:
    """Decode the Properties table into typed values so attribute reads (viewpoint
    conditions, scale styling) see what the entity actually declares. Ad-hoc types
    come from the `attribute-types` frontmatter map; undeclared cells decode
    leniently (numeric consumers coerce numeric strings)."""
    raw_props = parse_entity_content_sections(content_text)["properties"]
    if not raw_props:
        return {}
    attr_types_raw = frontmatter.get("attribute-types")
    attribute_types = (
        {str(k): str(v) for k, v in attr_types_raw.items()} if isinstance(attr_types_raw, dict) else {}
    )
    return decode_entity_properties(raw_props, {}, attribute_types)


def parse_outgoing_file(path: Path) -> list[ConnectionRecord]:
    """Parse an .outgoing.md file into individual ConnectionRecord entries."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []

    frontmatter = extract_yaml_block(content)
    if not frontmatter:
        return []

    source_entity = str(frontmatter.get("source-entity", ""))
    version = str(frontmatter.get("version", ""))
    status = str(frontmatter.get("status", "draft"))
    extra = {k: v for k, v in frontmatter.items() if k not in STANDARD_OUTGOING_FIELDS}
    last_updated = _canonical_stamp(frontmatter.get("last-updated"))

    records: list[ConnectionRecord] = []
    for decl in parse_connection_declarations(content):
        artifact_id = f"{stable_id(source_entity)}---{stable_id(decl.target_id)}@@{decl.conn_type}"
        specializations = applied_specialization_slugs(decl.metadata.get("specialization"))
        records.append(
            ConnectionRecord(
                artifact_id=artifact_id,
                source=source_entity,
                target=decl.target_id,
                conn_type=decl.conn_type,
                version=version,
                status=status,
                path=path,
                extra=extra,
                content_text=decl.description,
                associated_entities=decl.associated_entities,
                src_multiplicity=decl.src_multiplicity,
                tgt_multiplicity=decl.tgt_multiplicity,
                specializations=specializations,
                attributes={str(k): v for k, v in decl.metadata.items() if str(k) != "specialization"},
                last_updated=last_updated,
            )
        )
    return records


def parse_diagram(path: Path) -> DiagramRecord | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    frontmatter = extract_yaml_block(content)
    if not frontmatter:
        return None

    return DiagramRecord(
        artifact_id=str(frontmatter.get("artifact-id", path.stem)),
        artifact_type=str(frontmatter.get("artifact-type", "diagram")),
        name=str(frontmatter.get("name", "")),
        diagram_type=str(frontmatter.get("diagram-type", "")),
        version=str(frontmatter.get("version", "")),
        status=str(frontmatter.get("status", "draft")),
        path=path,
        extra={key: value for key, value in frontmatter.items() if key not in STANDARD_DIAGRAM_FIELDS},
        last_updated=_canonical_stamp(frontmatter.get("last-updated")),
    )


def parse_document(path: Path) -> DocumentRecord | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    frontmatter = extract_yaml_block(content)
    if not frontmatter:
        return None
    if str(frontmatter.get("artifact-type", "")).lower() != "document":
        return None
    doc_type = str(frontmatter.get("doc-type", "")).strip()
    if not doc_type:
        return None

    # Extract body (everything after the second ---)
    body = body_after_frontmatter(content).strip()

    sections = tuple(m.group(1).strip() for m in re.finditer(r"^##\s+(.+)$", body, re.MULTILINE))

    raw_kw = frontmatter.get("keywords", [])
    keywords: tuple[str, ...] = tuple(str(k) for k in (raw_kw if isinstance(raw_kw, list) else []))

    return DocumentRecord(
        artifact_id=str(frontmatter.get("artifact-id", path.stem)),
        doc_type=doc_type,
        title=str(frontmatter.get("title", path.stem)),
        status=str(frontmatter.get("status", "draft")),
        path=path,
        keywords=keywords,
        sections=sections,
        content_text=body,
        extra={k: v for k, v in frontmatter.items() if k not in STANDARD_DOCUMENT_FIELDS},
        last_updated=_canonical_stamp(frontmatter.get("last-updated")),
    )
