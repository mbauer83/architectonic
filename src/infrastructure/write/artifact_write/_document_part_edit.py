"""Editing one part of a stored document, for ``document.edit_document``.

A part edit — a section, a text, rows of a typed table (`src.application.artifacts.document_part_edits`)
— is made on the file as it is stored and leaves every byte it does not address as it was. So the
file is read here without newline translation, the body is spliced and never re-flowed, and the
frontmatter is touched in one place only: the `last-updated` stamp's own line, replaced where it
stands. Where the same call also changes a frontmatter field the block is written whole, as every
document edit writes it.

Links written with an artifact id are expanded in the text the caller sent and nowhere else, so an
edit of one section cannot rewrite a link in another.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.application.artifacts.document_part_edits import (
    DocumentEditRefused,
    PartEdit,
    SectionReplacement,
    TableRowEdits,
    TextReplacement,
    replace_section,
    replace_text,
)
from src.application.artifacts.document_schema import get_document_schema_object
from src.application.artifacts.document_table_edits import CellWriters, edit_table_rows
from src.application.artifacts.stored_ids import stored_id_reader
from src.application.document_links import ArtifactPathOf, as_link, id_links_expanded
from src.application.verification.artifact_verifier import ArtifactRegistry
from src.domain.repository.frontmatter import Frontmatter, body_after_frontmatter, read_frontmatter
from src.domain.repository.frontmatter import replace_frontmatter_text as _with_frontmatter_text

from .types import WriteResult

#: The stamp's own top-level line, up to a trailing comment, which is kept.
_STAMP_LINE = re.compile(r"^last-updated:[^#\r\n]*?(?=[ \t]*(?:#[^\r\n]*)?\r?$)", re.MULTILINE)


@dataclass(frozen=True)
class DocumentPartWriteResult(WriteResult):
    """A document write that also says which ids the rows it added were given."""

    added_row_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PartEdited:
    content: str
    added_row_ids: tuple[str, ...] = ()


def artifact_paths(repo_root: Path, registry: ArtifactRegistry | None) -> ArtifactPathOf:
    """Where an artifact's file is, asked of the registry in hand or of the repository's index."""

    def _path_of(artifact_id: str) -> Path | None:
        if registry is not None:
            return registry.find_file_by_id(artifact_id)
        from ._artifact_deduplication import get_repository  # noqa: PLC0415 — builds an index on first use

        return get_repository(repo_root).find_file_by_id(artifact_id)

    return _path_of


def read_as_stored(path: Path) -> str:
    """The file's text with its line endings as they are on disk."""
    return path.read_bytes().decode("utf-8")


def edit_part(
    stored: str, part: PartEdit, *, repo_root: Path, doc_type: str, doc_path: Path, path_of: ArtifactPathOf
) -> PartEdited:
    """`stored` with `part` made, id-form links in the caller's text stored as paths."""

    def _expanded(text: str) -> str:
        return id_links_expanded(text, written_to=doc_path.parent, path_of=path_of)

    match part:
        case SectionReplacement():
            return PartEdited(replace_section(stored, part.with_text(_expanded)))
        case TextReplacement():
            return PartEdited(replace_text(stored, part.with_text(_expanded)))
        case TableRowEdits():
            schema = get_document_schema_object(repo_root, doc_type)
            if schema is None:
                raise DocumentEditRefused(f"Document type '{doc_type}' is not declared here, so it declares no table.")
            writers = CellWriters(
                link_of=lambda stated: _expanded(as_link(stated)),
                stored_id_of=stored_id_reader(repo_root),
            )
            edited = edit_table_rows(stored, part, schema=schema, doc_path=doc_path, writers=writers)
            return PartEdited(edited.content, edited.added_row_ids)


def with_frontmatter(
    edited: str, *, stamp_line: str, whole_block: str | None, relocated: Callable[[str], str]
) -> str:
    """`edited` under its new frontmatter, its body passed through `relocated`.

    `whole_block` is the frontmatter YAML where the edit changed a field. Without one only the stamp
    moves: `stamp_line` takes the place of the `last-updated` line, and where the block has no such
    line of its own it is added as the block's last.
    """
    body = body_after_frontmatter(edited)
    head = edited[: len(edited) - len(body)]
    if whole_block is not None:
        return _with_frontmatter_text(head, whole_block) + relocated(body)
    reading = read_frontmatter(head)
    text = reading.text if isinstance(reading, Frontmatter) else ""
    stamped, replaced = _STAMP_LINE.subn(stamp_line, text, count=1)
    newline = "\r\n" if "\r\n" in head else "\n"
    return _with_frontmatter_text(head, stamped if replaced else f"{text}{newline}{stamp_line}") + relocated(body)
