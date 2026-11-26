"""What a repository holds of the shipped defaults, where each file goes, and how it is written.

The one owner of "write each shipped file that is missing, never overwrite": the workspace template
(at creation and on repair) and the repository upgrade's two ensure steps all ask it, so the next
shipped default is added in one place and every path writes it in the same bytes.

Two sets ship. Their scopes differ by caller, and stay the caller's to choose:

* the attribute and frontmatter schemata (`.arch-repo/schemata/`) — `shipped_schemata`;
* document types (`.arch-repo/documents/`) — `shipped_document_types`, over the schemas a caller
  names: the template writes the base and the assurance document types at creation, while its repair
  path and the upgrade step write the base set only.

An existing file is never read for differences here, let alone overwritten: an operator adapts these
files per repository, and a difference from the shipped default is their ordinary state.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA
from src.domain.repository.repo_layout import ARCH_DOC_SCHEMATA, ARCH_REPO, ARCH_SCHEMATA

#: Where the shipped attribute and frontmatter schemata go, relative to the repository root.
SCHEMATA_LOCATION = f"{ARCH_REPO}/{ARCH_SCHEMATA}"
#: Where the shipped document types go, relative to the repository root.
DOCUMENT_TYPES_LOCATION = f"{ARCH_REPO}/{ARCH_DOC_SCHEMATA}"


def shipped_text(payload: Mapping[str, object]) -> str:
    """The bytes a shipped default is written as: two-space JSON and a final newline."""
    return json.dumps(payload, indent=2) + "\n"


@dataclass(frozen=True)
class ShippedFile:
    """One shipped default: where it goes in a repository, and what it holds."""

    #: The file's path relative to the repository root, `/`-separated.
    location: str
    payload: Mapping[str, object]
    #: What the file is known by among its set: a schema's file name, a document type's name.
    key: str

    @property
    def name(self) -> str:
        return self.location.rsplit("/", 1)[-1]

    @property
    def text(self) -> str:
        return shipped_text(self.payload)


def shipped_schemata() -> tuple[ShippedFile, ...]:
    """The shipped attribute and frontmatter schemata, each at its place in a repository."""
    return tuple(
        ShippedFile(f"{SCHEMATA_LOCATION}/{name}", payload, key=name) for name, payload in DEFAULT_SCHEMATA.items()
    )


def shipped_document_types(schemas: Mapping[str, Mapping[str, object]]) -> tuple[ShippedFile, ...]:
    """The document types *schemas* names by type, each at its place in a repository."""
    return tuple(
        ShippedFile(f"{DOCUMENT_TYPES_LOCATION}/{doc_type}.json", schema, key=doc_type)
        for doc_type, schema in schemas.items()
    )


def missing_shipped(shipped: Iterable[ShippedFile], present: Callable[[str], bool]) -> tuple[ShippedFile, ...]:
    """The files of *shipped* a repository lacks, by *present* asked of each location."""
    return tuple(one for one in shipped if not present(one.location))


def ensure_shipped(
    shipped: Iterable[ShippedFile], *, present: Callable[[str], bool], write: Callable[[str, str], None],
) -> tuple[ShippedFile, ...]:
    """Write each file of *shipped* the repository lacks, never one it holds; answers those written."""
    missing = missing_shipped(shipped, present)
    for one in missing:
        write(one.location, one.text)
    return missing
