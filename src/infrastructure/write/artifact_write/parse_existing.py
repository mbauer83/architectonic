"""parse_existing.py — Parse existing entity/diagram files for editing.

Extracts structured components from entity .md files so that edit operations
can merge partial updates and re-format via the canonical formatter.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from src.domain.ontology_representation.specialization_values import applied_specialization_slugs
from src.domain.repository.connection_declaration import ConnectionDeclaration, parse_connection_declarations
from src.domain.yaml_documents import parse_yaml


@dataclass
class ParsedEntity:
    """Structured representation of an existing entity file."""

    frontmatter: dict[str, object]
    summary: str | None
    properties: dict[str, str]
    notes: str | None
    display_section_id: str
    display_content: str  # raw YAML string from the display block
    raw_text: str  # original file content for fallback


@dataclass
class ParsedOutgoing:
    """Structured representation of an existing .outgoing.md file."""

    frontmatter: dict[str, object]
    connections: list[
        dict[str, object]
    ]  # keys: connection_type, target_entity, description, optional src/tgt_multiplicity, associated_entities
    raw_text: str


@dataclass
class ParsedDiagram:
    """Structured representation of an existing diagram .puml file."""

    frontmatter: dict[str, object]
    puml_body: str  # everything after the frontmatter closing ---
    raw_text: str
    bindings: list  # list[Binding] — typed bindings parsed from frontmatter
    view_derivations: list  # list[ViewDerivation] — typed derivations parsed from frontmatter


@dataclass
class ParsedMatrix:
    """Structured representation of an existing matrix diagram .md file."""

    frontmatter: dict[str, object]
    matrix_markdown: str  # everything after the frontmatter closing ---
    raw_text: str


def parse_entity_file(path: Path) -> ParsedEntity:
    """Parse an entity .md file into structured components."""
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)

    # Extract sections by markers
    content_section = _extract_between(text, "<!-- §content -->", "<!-- §display -->")
    display_section = _extract_after(text, "<!-- §display -->")

    summary = _extract_summary(content_section, frontmatter.get("name", ""))
    properties = _extract_properties(content_section)
    notes = _extract_notes(content_section)
    display_section_id, display_content = _extract_display_block(display_section)

    return ParsedEntity(
        frontmatter=frontmatter,
        summary=summary,
        properties=properties,
        notes=notes,
        display_section_id=display_section_id,
        display_content=display_content,
        raw_text=text,
    )


def parse_outgoing_file(path: Path) -> ParsedOutgoing:
    """Parse an .outgoing.md file into structured components."""
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)

    connections_section = _extract_after(text, "<!-- §connections -->")
    connections = _parse_connection_sections(connections_section)

    return ParsedOutgoing(
        frontmatter=frontmatter,
        connections=connections,
        raw_text=text,
    )


def parse_diagram_file(path: Path) -> ParsedDiagram:
    """Parse a diagram .puml file into structured components."""
    from src.domain.diagrams.bindings import parse_bindings
    from src.domain.viewpoints.view_derivations import parse_view_derivations

    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)

    fm_end = _frontmatter_end_pos(text)
    puml_body = text[fm_end:] if fm_end else text

    raw_bindings = frontmatter.get("bindings")
    bindings = parse_bindings(raw_bindings if isinstance(raw_bindings, list) else None)

    raw_vds = frontmatter.get("view_derivations")
    view_derivations = parse_view_derivations(raw_vds if isinstance(raw_vds, list) else None)

    return ParsedDiagram(
        frontmatter=frontmatter,
        puml_body=puml_body,
        raw_text=text,
        bindings=bindings,
        view_derivations=view_derivations,
    )


def parse_matrix_file(path: Path) -> ParsedMatrix:
    """Parse a matrix diagram .md file into structured components."""
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    fm_end = _frontmatter_end_pos(text)
    matrix_markdown = text[fm_end:] if fm_end else text
    return ParsedMatrix(frontmatter=frontmatter, matrix_markdown=matrix_markdown, raw_text=text)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Extract YAML frontmatter from between --- markers."""
    m = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    if not m:
        return {}
    return parse_yaml(m.group(1)) or {}


def _frontmatter_end_pos(text: str) -> int:
    """Return the character position right after the closing --- of frontmatter."""
    m = re.match(r"^---\n.*?\n---\n", text, re.DOTALL)
    return m.end() if m else 0


def _extract_between(text: str, start_marker: str, end_marker: str) -> str:
    """Extract text between two markers (exclusive of markers)."""
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1:
        return ""
    return text[start + len(start_marker) : end]


def _extract_after(text: str, marker: str) -> str:
    """Extract text after a marker (exclusive of marker)."""
    pos = text.find(marker)
    if pos == -1:
        return ""
    return text[pos + len(marker) :]


def _extract_summary(content_section: str, entity_name: object) -> str | None:
    """Extract the summary paragraph(s) between the heading and ## Properties."""
    lines = content_section.strip().splitlines()
    collecting = False
    summary_lines: list[str] = []

    for line in lines:
        if line.startswith("## ") and not collecting:
            # This is the entity heading — start collecting after it
            collecting = True
            continue
        if collecting:
            if line.startswith("## "):
                # Hit the next section (Properties, Notes, etc.)
                break
            summary_lines.append(line)

    text = "\n".join(summary_lines).strip()
    return text if text else None


def _extract_properties(content_section: str) -> dict[str, str]:
    """Extract key-value pairs from the Properties table."""
    props: dict[str, str] = {}
    lines = content_section.splitlines()
    in_table = False

    for line in lines:
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


def _extract_notes(content_section: str) -> str | None:
    """Extract content from the Notes section."""
    lines = content_section.splitlines()
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

    text = "\n".join(notes_lines).strip()
    return text if text else None


def _extract_display_block(display_section: str) -> tuple[str, str]:
    """Extract section_id and raw YAML content from the §display block.

    Parses the ``### section_id`` header then the fenced YAML block beneath it.
    Returns ``("archimate", "")`` when no recognisable structure is found so that
    callers always receive a usable pair.
    """
    section_id = "archimate"
    h3 = re.search(r"^###\s+(\S+)", display_section, re.MULTILINE)
    if h3:
        section_id = h3.group(1)
    m = re.search(r"```ya?ml\n(.*?)```", display_section, re.DOTALL)
    content = m.group(1).strip() if m else ""
    return section_id, content


def _declaration_to_dict(decl: ConnectionDeclaration) -> dict[str, object]:
    """Convert a parsed declaration to the legacy connections-dict shape.

    Keys: connection_type, target_entity, description. src_multiplicity,
    tgt_multiplicity, metadata, and specialization are included only when present so that
    round-trip reformatting preserves them exactly.

    ``metadata`` carries the WHOLE per-connection metadata block. Keeping only the
    specialization out of it (as this used to) silently dropped every other declared
    attribute on any edit that reformatted the file — invisible data loss, and exactly the
    content a specialization-scoped metadata schema exists to describe. ``specialization``
    stays a separate key because the edit API sets and clears it by name; it is the
    authority for that one field when the file is written back.
    """
    conn: dict[str, object] = {
        "connection_type": decl.conn_type,
        "target_entity": decl.target_id,
        "description": decl.description,
    }
    if decl.src_multiplicity:
        conn["src_multiplicity"] = decl.src_multiplicity
    if decl.tgt_multiplicity:
        conn["tgt_multiplicity"] = decl.tgt_multiplicity
    if decl.associated_entities:
        conn["associated_entities"] = list(decl.associated_entities)
    if decl.metadata:
        conn["metadata"] = dict(decl.metadata)
    # Read whichever shape the file used — a scalar is the one-element case, a list is several
    # (ArchiMate §15.2). Accepting only the scalar dropped a list on the way back out: the
    # formatter treats this key as authoritative and *removes* the carried block's value when it
    # is absent, so re-rendering the file for any other connection in it silently unspecialized
    # the one carrying two.
    applied = applied_specialization_slugs(decl.metadata.get("specialization"))
    if applied:
        conn["specialization"] = list(applied)
    return conn


def _parse_connection_sections(connections_text: str) -> list[dict[str, object]]:
    """Parse H3 connection sections from the connections area of an .outgoing.md file.

    Each returned dict has keys: connection_type, target_entity, description.
    When multiplicities are present, src_multiplicity and tgt_multiplicity are
    also included so that round-trip reformatting preserves them.
    """
    return [_declaration_to_dict(decl) for decl in parse_connection_declarations(connections_text)]
