"""Shared markdown document-link extraction utilities."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord

MARKDOWN_LINK_RE = re.compile(r"(\[([^\]]*)\]\()([^)\s]+)(\))")
SECTION_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class MarkdownLink:
    label: str
    href: str
    start: int


@dataclass(frozen=True)
class DocumentEntityReference:
    document_id: str
    title: str
    doc_type: str
    path: str
    section: str
    label: str
    href: str

    def to_dict(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "doc_type": self.doc_type,
            "path": self.path,
            "section": self.section,
            "label": self.label,
            "href": self.href,
        }


def iter_markdown_links(content: str) -> list[MarkdownLink]:
    return [
        MarkdownLink(label=match.group(2), href=match.group(3), start=match.start())
        for match in MARKDOWN_LINK_RE.finditer(content)
    ]


def is_external_or_anchor_href(href: str) -> bool:
    return href.startswith(("http://", "https://", "#", "mailto:"))


def strip_anchor(href: str) -> str:
    anchor_index = href.find("#")
    return href[:anchor_index] if anchor_index >= 0 else href


def section_at_offset(content: str, offset: int) -> str:
    current = ""
    for match in SECTION_HEADING_RE.finditer(content):
        if match.start() > offset:
            break
        current = match.group(1).strip()
    return current


def references_to_entity(
    *,
    documents: list[DocumentRecord],
    entity: EntityRecord,
) -> list[DocumentEntityReference]:
    entity_path = entity.path.resolve()
    refs: list[DocumentEntityReference] = []
    for doc in documents:
        for link in iter_markdown_links(doc.content_text):
            if is_external_or_anchor_href(link.href):
                continue
            file_href = strip_anchor(link.href)
            if not file_href.endswith(".md"):
                continue
            try:
                target = (doc.path.parent / file_href).resolve()
            except OSError:
                continue
            if target != entity_path:
                continue
            refs.append(
                DocumentEntityReference(
                    document_id=doc.artifact_id,
                    title=doc.title,
                    doc_type=doc.doc_type,
                    path=str(doc.path),
                    section=section_at_offset(doc.content_text, link.start),
                    label=link.label,
                    href=link.href,
                )
            )
    return refs


def reference_dicts_for_entity(
    *,
    documents: Iterable[DocumentRecord],
    entity: EntityRecord,
) -> list[dict[str, str]]:
    return [ref.to_dict() for ref in references_to_entity(documents=list(documents), entity=entity)]
