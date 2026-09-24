"""Which kind of artifact a repository path holds, read from the layout alone: the one reading.

Four places used to answer this, and each answered differently: the incremental index treated every
`.md` it did not recognise as an entity, wherever it was; `artifact_verify` treated any `.puml` as
a diagram and any path through a `connections` directory as a connection; the pending-changes
classifier knew only the top-level `model/` and so reported no kind for an entity under
`projects/<slug>/model/`; the bulk candidate inventory made every non-diagram an entity. A file a
full scan never indexes could therefore enter the index as an entity after one incremental update.

The answer is positional and pure — no file is read and no directory listed — so a path that has
been deleted, or not written yet, classifies exactly as it will once it exists. A path outside the
layout is *not an artifact* (None), never a guess.
"""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath
from typing import Literal

from src.domain.repository.repo_layout import (
    ARTIFACT_SOURCE_SUFFIXES,
    DIAGRAM_CATALOG,
    DIAGRAMS,
    DOCS,
    ICONS,
    MODEL,
    OUTGOING_SUFFIX,
    PROJECTS,
    SCRATCHPAD_SUFFIX,
    SCRATCHPADS,
)

ArtifactKind = Literal["entity", "connection", "diagram", "document", "scratchpad", "icon"]


def artifact_kind_at(relative: PurePath | str) -> ArtifactKind | None:
    """The kind of artifact at *relative* (a path relative to its repository's root), or None."""
    path = PurePosixPath(PurePath(relative).as_posix())
    parts = path.parts
    if _is_under_a_model_root(parts):
        return model_file_kind(path)
    if parts[:1] == (DOCS,):
        return "document" if path.suffix == ".md" else None
    if parts[:2] == (DIAGRAM_CATALOG, DIAGRAMS):
        return "diagram" if path.suffix in ARTIFACT_SOURCE_SUFFIXES else None
    if parts[:2] == (DIAGRAM_CATALOG, ICONS) and len(parts) == 3:
        return "icon" if path.suffix == ".md" else None
    if parts[:1] == (SCRATCHPADS,):
        return "scratchpad" if path.name.endswith(SCRATCHPAD_SUFFIX) else None
    return None


def _is_under_a_model_root(parts: tuple[str, ...]) -> bool:
    """`model/…` or `projects/<slug>/model/…`, with at least a file below the root."""
    return (len(parts) > 1 and parts[0] == MODEL) or (len(parts) > 3 and parts[0] == PROJECTS and parts[2] == MODEL)


def model_file_kind(path: PurePath) -> Literal["entity", "connection"] | None:
    """Which of the two model-file kinds a file already known to sit under a model root is, by name.

    An entity's outgoing connections live beside it in `<entity>.outgoing.md`; every other `.md` there
    is an entity. The callers that walk a model root ask this rather than spell the suffix again.
    """
    if path.name.endswith(OUTGOING_SUFFIX):
        return "connection"
    return "entity" if path.suffix == ".md" else None
