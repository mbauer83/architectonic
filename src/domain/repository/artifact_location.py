"""The kinds of artifact a repository holds, declared once, and which of them a path holds.

**One row per kind.** A kind's facts used to be spelled where each was needed: the layout in a chain
of `if`s here, and everything that follows from *being* that kind as a `match` on its name at the
consumer — which kinds the verifier takes, which it verifies one file at a time, which move the
model's read-model generation, what prefix an id carries. Each consumer was right on the day it was
written and had to be found again for the next kind; the bulk candidate store's `match` had no arm
for an icon at all, and dropped one without having decided to. A consumer now asks the row for the
fact. `tests/architecture/test_nothing_branches_on_an_artifact_kind_name.py` holds that.

**A row holds what something reads today**, and nothing else: name, roots, placement, suffixes, the
id prefix where the kind has one of its own, how it is verified, and whether a change to it moves the
model generation. A kind's tier policy, the surfaces that carry it, its size limit and its format
window are facts of the same table and arrive with their first reader.

**The reading is positional and pure** — no file is read and no directory listed — so a path that has
been deleted, or not written yet, classifies exactly as it will once it exists. A path outside the
layout is *not an artifact* (None), never a guess. Four places used to answer this differently: the
incremental index treated every `.md` it did not recognise as an entity, `artifact_verify` any
`.puml` as a diagram, the pending-changes classifier knew only the top-level `model/`, and the bulk
candidate inventory made every non-diagram an entity.

`artifact_kind_consistency` refuses a table whose rows contradict one another; it runs at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath
from typing import Literal, TypeIs

from src.domain.repository.repo_layout import (
    ARTIFACT_SOURCE_SUFFIXES,
    DIAGRAM_CATALOG,
    DIAGRAMS,
    DOCS,
    ICONS,
    MANAGED_INCLUDE_BASENAMES,
    MODEL,
    OUTGOING_SUFFIX,
    PROJECTS,
    RENDERED,
    RENDERED_SUFFIXES,
    SCRATCHPAD_SUFFIX,
    SCRATCHPADS,
)

#: The public list of kind names. A `Literal` because typed contracts need one and a type cannot be
#: computed from the rows; `tests/domain/test_the_kind_table.py` holds it equal to them.
ArtifactKindName = Literal[
    "entity", "connection", "diagram", "document", "icon", "candidate-architecture", "scratchpad"
]

#: The kinds the artifact verifier takes — the rows whose `verification` is not `unverified`, as a
#: type, for the same reason and held equal by the same test.
VerifiedArtifactKindName = Literal["entity", "connection", "diagram", "document", "icon", "candidate-architecture"]

#: How the artifact verifier treats a kind. `with-the-model`: inside the model inventory, against the
#: graph, with per-file state reused between passes. `standalone`: one file at a time beside it, on
#: every pass. `unverified`: not by the artifact verifier at all.
Verification = Literal["with-the-model", "standalone", "unverified"]

#: Where under a root a kind's files may sit: at any depth, or only in the root directory itself.
Placement = Literal["anywhere-below", "directly-below"]

#: In a root, the segment that stands for any one directory name: `projects/<slug>/model`.
ANY_DIRECTORY = "*"


@dataclass(frozen=True, slots=True)
class KindDeclaration:
    """One kind of artifact: where its files are, how its ids begin, and the facts consumers ask."""

    name: ArtifactKindName
    #: Directories the kind's files live under, as segments from the repository root.
    roots: tuple[tuple[str, ...], ...]
    placement: Placement
    #: What a file's name ends in. Where two kinds share a root, the longer matching suffix decides.
    suffixes: tuple[str, ...]
    #: The prefix every id of this kind carries, where the kind has one of its own. None where the
    #: prefix belongs to a type within the kind (an entity type's, a document type's abbreviation, a
    #: diagram type's) or the kind has no id of its own (a connection is its triple).
    id_prefix: str | None
    verification: Verification
    #: Whether a change to a file of this kind is a change to the model's read-model.
    moves_model_generation: bool

    identity_field: str = "artifact-id"
    generated_paths: tuple[str, ...] = ()

    def file_identity(self, path: PurePath) -> str:
        """The identity carried by the file name, excluding the kind's full suffix."""
        suffix = self.suffix_carried_by(path)
        return path.name.removesuffix(suffix) if suffix else path.stem

    def may_hold(self, parts: tuple[str, ...]) -> bool:
        """Whether a file at *parts* sits where this kind's files do, whatever its name."""
        return any(_sits_under(parts, root, self.placement) for root in self.roots)

    def suffix_carried_by(self, path: PurePath) -> str | None:
        """The longest of this kind's suffixes *path* carries, or None."""
        carried = [suffix for suffix in self.suffixes if _carries(path, suffix)]
        return max(carried, key=len) if carried else None


_MODEL_ROOTS = ((MODEL,), (PROJECTS, ANY_DIRECTORY, MODEL))

ARTIFACT_KINDS: tuple[KindDeclaration, ...] = (
    KindDeclaration(
        name="entity", roots=_MODEL_ROOTS, placement="anywhere-below", suffixes=(".md",),
        id_prefix=None, verification="with-the-model", moves_model_generation=True,
    ),
    # An entity's outgoing connections live beside it in `<entity>.outgoing.md`.
    KindDeclaration(
        name="connection", roots=_MODEL_ROOTS, placement="anywhere-below", suffixes=(OUTGOING_SUFFIX,),
        id_prefix=None, verification="with-the-model", moves_model_generation=True, identity_field="source-entity",
    ),
    KindDeclaration(
        name="diagram", roots=((DIAGRAM_CATALOG, DIAGRAMS),), placement="anywhere-below",
        suffixes=tuple(sorted(ARTIFACT_SOURCE_SUFFIXES)),
        id_prefix=None, verification="with-the-model", moves_model_generation=True,
        generated_paths=(
            *(f"{DIAGRAM_CATALOG}/{RENDERED}/**/*{suffix}" for suffix in RENDERED_SUFFIXES),
            *(f"{DIAGRAM_CATALOG}/{name}" for name in sorted(MANAGED_INCLUDE_BASENAMES)),
        ),
    ),
    KindDeclaration(
        name="document", roots=((DOCS,),), placement="anywhere-below", suffixes=(".md",),
        id_prefix=None, verification="standalone", moves_model_generation=True,
    ),
    KindDeclaration(
        name="icon", roots=((DIAGRAM_CATALOG, ICONS),), placement="directly-below", suffixes=(".md",),
        id_prefix="ICO", verification="standalone", moves_model_generation=True,
    ),
    KindDeclaration(
        name="candidate-architecture", roots=(("candidate-architectures",),), placement="directly-below",
        suffixes=(".candidate.yaml",), id_prefix="CAND", verification="standalone",
        moves_model_generation=False, identity_field="id",
    ),
    # Not model content: unlisted by `list_artifacts`, ranked below everything in search, and saved
    # about once a second while someone is thinking — so its changes move a generation of their own.
    KindDeclaration(
        name="scratchpad", roots=((SCRATCHPADS,),), placement="anywhere-below", suffixes=(SCRATCHPAD_SUFFIX,),
        id_prefix="SCR", verification="unverified", moves_model_generation=False,
    ),
)

#: Every kind's name, in the table's order — what a contract enumerates.
ARTIFACT_KIND_NAMES: tuple[ArtifactKindName, ...] = tuple(kind.name for kind in ARTIFACT_KINDS)

_BY_NAME: dict[ArtifactKindName, KindDeclaration] = {kind.name: kind for kind in ARTIFACT_KINDS}


def artifact_kind(name: ArtifactKindName) -> KindDeclaration:
    """The row for the kind called *name*."""
    return _BY_NAME[name]


def own_id_prefix(name: ArtifactKindName) -> str:
    """The id prefix the kind called *name* declares for itself.

    For a kind's own code, which knows it has one. A kind whose ids take a type's prefix has no answer
    here, and asking is a programming error rather than a case to handle.
    """
    prefix = _BY_NAME[name].id_prefix
    if prefix is None:
        raise LookupError(f"the kind {name!r} declares no id prefix of its own; its ids take a type's")
    return prefix


def is_verified_kind(name: ArtifactKindName) -> TypeIs[VerifiedArtifactKindName]:
    """Whether the artifact verifier takes files of the kind called *name*."""
    return _BY_NAME[name].verification != "unverified"


def artifact_kind_declared_at(
    relative: PurePath | str, kinds: tuple[KindDeclaration, ...] = ARTIFACT_KINDS
) -> KindDeclaration | None:
    """The row of the kind a path relative to its repository's root holds, or None."""
    path = PurePosixPath(PurePath(relative).as_posix())
    return _most_specific(path, tuple(kind for kind in kinds if kind.may_hold(path.parts)))


def owner_of_generated_path(relative: PurePath) -> KindDeclaration | None:
    """The kind whose generated output occupies this path, separately from its verifiable sources."""
    return next((kind for kind in ARTIFACT_KINDS if any(relative.full_match(p) for p in kind.generated_paths)), None)


def artifact_kind_at(relative: PurePath | str) -> ArtifactKindName | None:
    """The kind of artifact at *relative* (a path relative to its repository's root), or None."""
    declared = artifact_kind_declared_at(relative)
    return declared.name if declared is not None else None


def model_file_kind(path: PurePath) -> ArtifactKindName | None:
    """Which of the kinds a model root holds a file already known to sit under one is, by name.

    An entity's outgoing connections live beside it in `<entity>.outgoing.md`; every other `.md` there
    is an entity. The callers that walk a model root ask this rather than spell the suffix again.
    """
    declared = _most_specific(path, tuple(kind for kind in ARTIFACT_KINDS if kind.roots == _MODEL_ROOTS))
    return declared.name if declared is not None else None


def source_globs(kind: KindDeclaration) -> tuple[str, ...]:
    """Glob patterns, relative to a repository's root, that between them find every file of *kind*.

    For whoever lists a kind's files: the walk is theirs, where to walk and for what is the row's.
    """
    depth = "**/" if kind.placement == "anywhere-below" else ""
    return tuple(f"{'/'.join(root)}/{depth}*{suffix}" for root in kind.roots for suffix in kind.suffixes)


def roots_overlap(one: tuple[str, ...], other: tuple[str, ...]) -> bool:
    """Whether a file could sit under both roots: one leads into the other, segment by segment."""
    return all(a == b or ANY_DIRECTORY in (a, b) for a, b in zip(one, other, strict=False))


def _most_specific(path: PurePath, candidates: tuple[KindDeclaration, ...]) -> KindDeclaration | None:
    """Among *candidates*, the kind whose suffix claims most of the file's name."""
    claims = [(len(suffix), kind) for kind in candidates if (suffix := kind.suffix_carried_by(path)) is not None]
    return max(claims, key=lambda claim: claim[0])[1] if claims else None


def _sits_under(parts: tuple[str, ...], root: tuple[str, ...], placement: Placement) -> bool:
    below = len(parts) - len(root)
    if below < 1 or (placement == "directly-below" and below != 1):
        return False
    return all(segment in (ANY_DIRECTORY, part) for segment, part in zip(root, parts, strict=False))


def _carries(path: PurePath, suffix: str) -> bool:
    """Whether the file's name ends in *suffix*.

    A plain extension is read as `pathlib` reads one, so a file named only `.md` has none; a compound
    suffix is the end of the name. Both as the readings this table replaced had them.
    """
    return path.suffix == suffix if suffix.count(".") == 1 else path.name.endswith(suffix)
