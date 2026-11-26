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
* what refers to something *that is not there* — **W155**, in `check_internal_links`.

The third was listed here as W158, a code that was never minted: the fact already had a rule and a
number, and giving it a second would have meant two vocabularies for one finding. W155 was a
document-only, `.md`-only regex when this docstring was written, which is what made it look like a
different question; it became a filter over `references_from` and grew to every artifact source, so
it now answers the whole of it — for a diagram's prose as much as a document's.

The next filter is reference-typed attributes, which would otherwise have been the fourth reading
of one question.

`relocated_links` is the same reading turned round: a link is a statement about two locations, where
it is written and what it addresses, and a move changes one of them. It is here because rewriting a
link is reading it first, and the rewriting that lived beside the rename compared the href whole — so
a link carrying a `#section` was never found, the defect this module was created to end.

`id_links_expanded` is the reading turned to the write: a link may be *written* with an artifact id
where its path would go, and is stored as the relative path every reader above resolves. One stored
form, so none of them learns a second; the id form exists only between an author and the write path.
An id that names nothing has no path and is left as written; `unresolved_id_links` names each one, so
the write that would leave it can refuse it.

`resolve_artifact_links` is the step past "what does the prose point at" to "what is the thing it
points at" — one reading of a linked file's frontmatter, classifying it as an entity, a document or
a diagram and naming its type. It lives beside `references_from` rather than beside the rule that
first wanted it, because the required-reference rules, the promotion closure and the write-time
placeholder all ask it, and the entity-only form they used to share could not tell a linked diagram
from a linked entity at all: it reported every artifact's `artifact-type`, so a link to a diagram
contributed the literal type `diagram` to the set an entity term was matched against.
"""

from __future__ import annotations

import os.path
import posixpath
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from src.domain.artifact_id import is_entity_id
from src.domain.diagrams.diagram_type_field import stated_diagram_type
from src.domain.icons.icon_file import ICON_ARTIFACT_TYPE
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from src.domain.repository.frontmatter import parse_frontmatter
from src.domain.repository.repo_layout import ARTIFACT_SOURCE_SUFFIXES

#: What a resolved link turned out to address. The same three vocabularies a required-reference term
#: may name, which is the join: a term of one kind is satisfied only by a link of that kind.
ArtifactLinkKind = Literal["entity", "document", "diagram"]

MARKDOWN_LINK_RE = re.compile(r"(\[([^\]]*)\]\()([^)\s]+)(\))")
SECTION_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
#: A section's heading or one beneath it: its level, then its title. The same reading as the line
#: above at level two, so what is a section does not depend on which of the two was asked.
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$", re.MULTILINE)


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


_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[/\\]")


def is_absolute_href(href: str) -> bool:
    """Whether *href* names a place on one machine rather than a file relative to its document."""
    return href.startswith(("/", "file://")) or bool(_WINDOWS_ABSOLUTE_PATH_RE.match(href))


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


def _lexical(path: Path) -> Path:
    """An absolute path with `.`/`..` collapsed textually, following no symlink."""
    return Path(os.path.normpath(path.absolute()))


def relocated_links(
    content: str, *, read_from: Path, written_to: Path, moves: Mapping[Path, Path]
) -> str:
    """*content* with each relative link re-expressed so it addresses, from *written_to*, the file
    it addressed from *read_from* — or that file's new path, where *moves* says it has one.

    Both halves of a move are this one question. The text that moved is read from its old directory
    and written to its new one; a text that stayed has `read_from == written_to` and only *moves*
    says anything. A link neither half touches keeps its author's spelling, and so do external,
    anchor-only and absolute hrefs, which address nothing relative. A `#section` is carried across.

    Paths are compared **lexically**, not through `Path.resolve()`. A markdown link is a lexical
    relative path, and following symlinks conflates two different files whenever the repository is
    reached through one: inside a batch transaction the staging tree symlinks live files in, so a
    link resolved through the symlink landed on the live file while the moved-from path — deleted
    by the rename — resolved to itself, and no link in any document was rewritten.
    """
    old_directory, new_directory = _lexical(read_from), _lexical(written_to)
    moved_targets = {_lexical(old): _lexical(new) for old, new in moves.items()}

    def _relocated(match: re.Match[str]) -> str:
        href = match.group(3)
        file_href = strip_anchor(href)
        if not file_href or is_external_or_anchor_href(href) or is_absolute_href(href):
            return match.group(0)
        old_target = _lexical(old_directory / file_href)
        new_target = moved_targets.get(old_target, old_target)
        if new_target == old_target and new_directory == old_directory:
            return match.group(0)
        relocated = posixpath.relpath(new_target.as_posix(), new_directory.as_posix())
        return f"{match.group(1)}{relocated}{href[len(file_href):]}{match.group(4)}"

    return MARKDOWN_LINK_RE.sub(_relocated, content)


#: Where an artifact's file is, by its id in full or short form; `None` for an id that names nothing.
ArtifactPathOf = Callable[[str], Path | None]


def as_link(reference: str) -> str:
    """A reference stated as a markdown link or as an artifact id alone, as a link.

    The id alone becomes a link with no label, which `id_links_expanded` labels with the artifact's name.
    """
    stated = reference.strip()
    return stated if iter_markdown_links(stated) else f"[]({stated})"


def _named(target: Path, artifact_id: str) -> str:
    frontmatter = _frontmatter_of(target) or {}
    return str(frontmatter.get("name") or frontmatter.get("title") or artifact_id)


def _written_by_id(href: str, directory: Path) -> str | None:
    """The artifact id *href* is written with, or `None` where it is a path.

    An href that names a file beside the document is a path whatever it is called: `ADR@1.x.md` is
    spelled like a short id with the slug `md`.
    """
    artifact_id = strip_anchor(href)
    return artifact_id if is_entity_id(artifact_id) and not (directory / artifact_id).exists() else None


def id_links_expanded(content: str, *, written_to: Path, path_of: ArtifactPathOf) -> str:
    """*content* with each link whose href is an artifact id stored as the relative path from *written_to*.

    `[the decision](ADR@1783406789.aBcDeF)` becomes `[the decision](../adr/ADR@1783406789.aBcDeF.slug.md)`.
    Either id form is taken, a `#section` is carried across, and a link with no label is given the
    artifact's name. Every other link keeps its author's spelling, and so does an href that names a
    file beside the document — a file is what a path means, whatever it is called.

    An id that names nothing keeps its spelling too: it has no path to be stored as. Whether a write
    may leave it is the write's question, and `unresolved_id_links` is how it is asked.
    """
    directory = _lexical(written_to)

    def _expanded(match: re.Match[str]) -> str:
        href = match.group(3)
        artifact_id = _written_by_id(href, directory)
        target = path_of(artifact_id) if artifact_id is not None else None
        if artifact_id is None or target is None:
            return match.group(0)
        stored = posixpath.relpath(_lexical(target).as_posix(), directory.as_posix())
        label = match.group(2) or _named(target, artifact_id)
        return f"[{label}]({stored}{href[len(artifact_id):]}{match.group(4)}"

    return MARKDOWN_LINK_RE.sub(_expanded, content)


def unresolved_id_links(content: str, *, written_to: Path, path_of: ArtifactPathOf) -> list[str]:
    """Each artifact id a link in *content* is written with that names no artifact, once, in order.

    Stored as written such a link is a path to no file, with a suffix the unresolvable-link rule does
    not watch, so nothing would ever report it. The text asked is the whole of what a write leaves —
    a part edit leaves the parts it does not address as they were, and a link in one of them is left
    by the write as surely as one it was sent.
    """
    directory = _lexical(written_to)
    stated = (_written_by_id(link.href, directory) for link in iter_markdown_links(content))
    named_by_nothing = (artifact_id for artifact_id in stated if artifact_id and path_of(artifact_id) is None)
    return list(dict.fromkeys(named_by_nothing))


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
        diagram_type = stated_diagram_type(fm)
        return ("diagram", diagram_type) if diagram_type else None
    if artifact_type == ICON_ARTIFACT_TYPE:
        return None  # a picture of the library, not model content: linked as an image would be
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
        suffix = Path(strip_anchor(reference.href)).suffix
        if suffix not in ARTIFACT_SOURCE_SUFFIXES or not reference.target.is_file():
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
