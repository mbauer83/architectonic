"""connection_declaration.py — the one connection-declaration grammar.

An ``.outgoing.md`` file body is a sequence of ``### <header>`` sections, one
per connection: a header line (connection type, optional source/target
multiplicity, target artifact id), an optional fenced ``metadata`` YAML block
(per-connection data; file frontmatter is shared across connections and
must never carry it) immediately under the heading, then a body (free-text
description plus ``<!-- §assoc ID -->`` second-order association markers).
Every reader, writer, and verifier of that shape goes through
``parse_connection_declarations`` / ``format_connection_declaration`` here —
no private header regex elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml  # type: ignore[import-untyped]

_HEADER_RE = re.compile(
    r"^(?P<conn_type>[a-z][a-z0-9-]+)"
    r"(?:\s+\[(?P<src_mult>[^\]]+)\])?"
    r"\s+→\s+"
    r"(?:\[(?P<tgt_mult>[^\]]+)\]\s+)?"
    r"(?P<target_id>\S+)$"
)
_ASSOC_RE = re.compile(r"<!--\s*§assoc\s+(\S+)\s*-->")
_HEADING_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_METADATA_BLOCK_RE = re.compile(r"\A[ \t]*\n*```yaml\n(.*?)\n```[ \t]*\n?", re.DOTALL)


@dataclass(frozen=True)
class ConnectionDeclaration:
    """One parsed ``### <header>`` section of an .outgoing.md file."""

    conn_type: str
    target_id: str
    src_multiplicity: str = ""
    tgt_multiplicity: str = ""
    description: str = ""
    associated_entities: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_connection_header(header: str) -> ConnectionDeclaration | None:
    """Parse a single header line (no body) — e.g. for header-only validation.

    Returns ``None`` when *header* does not match the grammar.
    """
    m = _HEADER_RE.match(header.strip())
    if not m:
        return None
    return ConnectionDeclaration(
        conn_type=m.group("conn_type"),
        target_id=m.group("target_id"),
        src_multiplicity=m.group("src_mult") or "",
        tgt_multiplicity=m.group("tgt_mult") or "",
    )


@dataclass(frozen=True)
class _MetadataFenceOutcome:
    """Three-way result of attempting to parse a section's leading fenced block: no fence
    present at all, a fence that parsed to *data* (a mapping, possibly empty), or a fence
    present whose content failed to parse as a mapping (``malformed=True``)."""

    present: bool
    data: dict[str, Any]
    remainder: str
    malformed: bool = False


def _parse_metadata_fence(section_text: str) -> _MetadataFenceOutcome:
    m = _METADATA_BLOCK_RE.match(section_text)
    if not m:
        return _MetadataFenceOutcome(present=False, data={}, remainder=section_text)
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return _MetadataFenceOutcome(present=True, data={}, remainder=section_text, malformed=True)
    if not isinstance(data, dict):
        return _MetadataFenceOutcome(present=True, data={}, remainder=section_text, malformed=True)
    return _MetadataFenceOutcome(present=True, data=data, remainder=section_text[m.end() :])


def _extract_metadata_block(section_text: str) -> tuple[dict[str, Any], str]:
    """Split a leading fenced ```yaml metadata block off *section_text*, if present.

    Returns ``({}, section_text)`` unchanged when no metadata block is present, the block
    is malformed, or it does not parse to a mapping — the text is then handled as ordinary
    body prose, never silently dropped.
    """
    outcome = _parse_metadata_fence(section_text)
    return outcome.data, outcome.remainder


def find_malformed_metadata_sections(text: str) -> list[str]:
    """Return the header text of every section whose leading fenced ```yaml metadata block
    is present but fails to parse as a mapping.

    ``parse_connection_declarations`` reinterprets that exact shape as ordinary body prose
    (by design, so a broken block never crashes a read) — which means a metadata block that
    fails to parse silently vanishes rather than surfacing anywhere. This is the read-only
    detector's hook for reporting it instead.
    """
    headings = list(_HEADING_RE.finditer(text))
    malformed: list[str] = []
    for i, m in enumerate(headings):
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        if _parse_metadata_fence(text[body_start:body_end]).malformed:
            malformed.append(m.group(1))
    return malformed


def parse_connection_declarations(text: str) -> list[ConnectionDeclaration]:
    """Parse every ``### `` section in *text* into a ``ConnectionDeclaration``.

    *text* is the connections area of an .outgoing.md file (frontmatter
    already stripped). Sections whose header does not match the grammar are
    skipped, matching prior lenient behavior.
    """
    declarations: list[ConnectionDeclaration] = []
    headings = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        parsed = parse_connection_header(m.group(1))
        if parsed is None:
            continue
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        section_text = text[body_start:body_end]
        metadata, remainder = _extract_metadata_block(section_text)
        body = remainder.strip()
        assoc = tuple(_ASSOC_RE.findall(body))
        clean_body = _ASSOC_RE.sub("", body).strip()
        declarations.append(
            ConnectionDeclaration(
                conn_type=parsed.conn_type,
                target_id=parsed.target_id,
                src_multiplicity=parsed.src_multiplicity,
                tgt_multiplicity=parsed.tgt_multiplicity,
                description=clean_body,
                associated_entities=assoc,
                metadata=metadata,
            )
        )
    return declarations


def format_connection_declaration(decl: ConnectionDeclaration) -> str:
    """Format one declaration as a ``### header`` section (header + metadata + body)."""
    src_part = f" [{decl.src_multiplicity}]" if decl.src_multiplicity else ""
    tgt_part = f"[{decl.tgt_multiplicity}] " if decl.tgt_multiplicity else ""
    lines = [f"### {decl.conn_type}{src_part} → {tgt_part}{decl.target_id}"]
    if decl.metadata:
        yaml_text = str(yaml.safe_dump(dict(decl.metadata), sort_keys=False)).strip()
        lines.append("")
        lines.append(f"```yaml\n{yaml_text}\n```")
    if decl.description:
        lines.append("")
        lines.append(decl.description)
    for assoc_id in decl.associated_entities:
        lines.append(f"<!-- §assoc {assoc_id} -->")
    return "\n".join(lines)
