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

`resolve_artifact_links` is the step past "what does the prose point at" to "what is the thing it
points at" — one reading of a linked file's frontmatter, classifying it as an entity, a document or
a diagram and naming its type. It lives beside `references_from` rather than beside the rule that
first wanted it, because the required-reference rules, the promotion closure and the write-time
placeholder all ask it, and the entity-only form they used to share could not tell a linked diagram
from a linked entity at all: it reported every artifact's `artifact-type`, so a link to a diagram
contributed the literal type `diagram` to the set an entity term was matched against.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from src.domain.repository.frontmatter import parse_frontmatter

#: What a resolved link turned out to address. The same three vocabularies a required-reference term
#: may name, which is the join: a term of one kind is satisfied only by a link of that kind.
ArtifactLinkKind = Literal["entity", "document", "diagram"]

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


@dataclass(frozen=True)
class ResolvedArtifactLink:
    """One markdown link that resolves to an artifact file, and what that artifact is.

    `type_name` is the type within the link's own vocabulary — the entity type, the `doc-type`, or
    the `diagram-type`. Three vocabularies that do not share a namespace, which is why the kind is
    carried beside the name rather than folded into it.
    """

    href: str
    artifact_id: str
    kind: ArtifactLinkKind
    type_name: str
    name: str


def _frontmatter_of(target: Path) -> dict[str, object] | None:
    """The linked file's frontmatter, or ``None`` when it is unreadable or not YAML.

    A malformed *linked* file is not a finding about the document that links it, so this answers
    nothing rather than raising into whatever asked. The tolerance is deliberate and was already the
    behaviour of the entity-only reading this replaced.
    """
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return parse_frontmatter(content)
    except yaml.YAMLError:
        return None


def _classify(fm: dict[str, object]) -> tuple[ArtifactLinkKind, str] | None:
    """Which vocabulary a linked artifact belongs to, and its type within it."""
    artifact_type = str(fm.get("artifact-type") or "").strip()
    if not artifact_type:
        return None
    if artifact_type == "document":
        doc_type = str(fm.get("doc-type") or "").strip()
        return ("document", doc_type) if doc_type else None
    if artifact_type == "diagram":
        diagram_type = str(fm.get("diagram-type") or "").strip()
        return ("diagram", diagram_type) if diagram_type else None
    return ("entity", artifact_type)


def resolve_artifact_links(doc_path: Path, content: str) -> list[ResolvedArtifactLink]:
    """Every markdown link in *content* that resolves to an artifact, classified by what it is.

    The single reading of "what model content does this document reach". `references_from` answers
    what the prose points at; this one opens each target and says whether it is an entity, a document
    or a diagram, and of which type. Non-artifact targets — an image, a plain markdown file, an
    `.outgoing.md` carrying no `artifact-type`, a path that is not there — resolve to nothing.

    The target's own frontmatter rather than the artifact index, which does hold a path→id map: the
    verifier's document rules take an optional registry and run over a *staging* directory during
    write-time preview, where the document is not indexed and its links reach out of the staged tree
    entirely. The index answers what is indexed; this answers what a file is.
    """
    links: list[ResolvedArtifactLink] = []
    for reference in references_from(content, directory=doc_path.parent):
        if not strip_anchor(reference.href).endswith(".md") or not reference.target.is_file():
            continue
        fm = _frontmatter_of(reference.target)
        if fm is None:
            continue
        classified = _classify(fm)
        if classified is None:
            continue
        kind, type_name = classified
        artifact_id = str(fm.get("artifact-id", ""))
        links.append(
            ResolvedArtifactLink(
                href=reference.href,
                artifact_id=artifact_id,
                kind=kind,
                type_name=type_name,
                name=str(fm.get("name", fm.get("title", artifact_id))),
            )
        )
    return links


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
