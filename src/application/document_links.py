"""What a document's prose refers to. One reading, for every caller.

There were two, and they answered the same question differently. `references_to_entity` parsed the
markdown link whole — label, href, offset — dropped external and anchor-only hrefs, and stripped a
`#section` before resolving. `find_broken_links`, in the cascade-delete path, matched
`](…​.md)` with a regex of its own, which cannot match `](…​.md#properties)` at all: a document
linking into a *section* of an entity was invisible to the check that exists to find what a
deletion would break.

So the reading lives here once, as `references_from`, and each caller is a filter over it:

* what refers to *this entity* — the document context read;
* what refers to something *about to be deleted* — the cascade preflight;
* what refers to something *that is not there* — W158.

The next filter is reference-typed attributes, which would otherwise have been the fourth reading
of one question.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class DocumentReference:
    """One link a document's prose makes, and the file it addresses.

    `target` is absolute and resolved against the document's own directory, which is how such a
    link is *read* — in a checkout, on a forge and in the application alike. It says nothing about
    whether the file exists; that is a question for whoever is asking.
    """

    label: str
    href: str
    start: int
    target: Path


def references_from(content: str, *, directory: Path) -> list[DocumentReference]:
    """Every file a document's prose points at, resolved against the document's own directory.

    External and anchor-only hrefs address nothing on disk and are left out. A `#section` suffix
    is stripped before resolving, because the file is what a link resolves to and the section is
    where it lands inside it — the reading that had its own regex could not match one at all.
    """
    references: list[DocumentReference] = []
    for link in iter_markdown_links(content):
        if is_external_or_anchor_href(link.href):
            continue
        file_href = strip_anchor(link.href)
        if not file_href:
            continue
        try:
            target = (directory / file_href).resolve()
        except OSError:
            continue
        references.append(
            DocumentReference(label=link.label, href=link.href, start=link.start, target=target)
        )
    return references


def references_to_entity(
    *,
    documents: list[DocumentRecord],
    entity: EntityRecord,
) -> list[DocumentEntityReference]:
    """The documents whose prose links to *entity*, and where in each the link sits."""
    entity_path = entity.path.resolve()
    return [
        DocumentEntityReference(
            document_id=doc.artifact_id,
            title=doc.title,
            doc_type=doc.doc_type,
            path=str(doc.path),
            section=section_at_offset(doc.content_text, reference.start),
            label=reference.label,
            href=reference.href,
        )
        for doc in documents
        for reference in references_from(doc.content_text, directory=doc.path.parent)
        if reference.target == entity_path
    ]


def reference_dicts_for_entity(
    *,
    documents: Iterable[DocumentRecord],
    entity: EntityRecord,
) -> list[dict[str, str]]:
    return [ref.to_dict() for ref in references_to_entity(documents=list(documents), entity=entity)]
