"""Whether the kind table can mean what it says: the contradictions rows can hold among themselves.

Every reading of the table assumes these and none of them checks: that a path has one kind, that an
id prefix names one, that a name finds one row. A table that breaks one still loads, and what it gets
wrong is whichever consumer happens to ask first — a file indexed as one kind and verified as
another, an id whose kind depends on dictionary order. So the table is asked once, at startup, and a
contradiction is a refusal that names the rows and what to change.

Pure, and about the rows only. What a prefix collides with *outside* the table — an entity type's, a
document type's — needs the catalogues, and is `application._startup_kind_table_consistency`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from itertools import combinations
from typing import get_args

from src.domain.artifact_id import PREFIX_PATTERN
from src.domain.repository.artifact_location import (
    ArtifactKindName,
    KindDeclaration,
    VerifiedArtifactKindName,
    roots_overlap,
)

_ID_PREFIX = re.compile(rf"^{PREFIX_PATTERN}$")


def kind_table_contradictions(kinds: tuple[KindDeclaration, ...]) -> list[str]:
    """Every way *kinds* contradicts itself, each as a sentence naming the rows and the fix."""
    return [
        *_repeated_names(kinds),
        *_names_the_public_lists_disagree_on(kinds),
        *_rows_that_cannot_hold_a_file(kinds),
        *_shared_paths(kinds),
        *_shared_id_prefixes(kinds),
        *_impossible_facts(kinds),
    ]


def _repeated_names(kinds: tuple[KindDeclaration, ...]) -> Iterator[str]:
    names = [kind.name for kind in kinds]
    for name in sorted({name for name in names if names.count(name) > 1}):
        yield (
            f"Kind table: {names.count(name)} rows are named {name!r}. A name finds one row; "
            "merge the rows or rename all but one."
        )


def _names_the_public_lists_disagree_on(kinds: tuple[KindDeclaration, ...]) -> Iterator[str]:
    """The two `Literal`s contracts are typed by must be the table's, or a contract names what is not there."""
    declared = {kind.name for kind in kinds}
    verified = {kind.name for kind in kinds if kind.verification != "unverified"}
    for label, listed, expected in (
        ("ArtifactKindName", set(get_args(ArtifactKindName)), declared),
        ("VerifiedArtifactKindName", set(get_args(VerifiedArtifactKindName)), verified),
    ):
        if listed != expected:
            yield (
                f"Kind table: `{label}` lists {sorted(listed)} and the rows give {sorted(expected)}. "
                f"Make `{label}` in `artifact_location` name exactly the rows it is derived from."
            )


def _rows_that_cannot_hold_a_file(kinds: tuple[KindDeclaration, ...]) -> Iterator[str]:
    for kind in kinds:
        if not kind.roots or any(not root for root in kind.roots):
            yield (
                f"Kind table: the row {kind.name!r} has no root directory, so it would claim files "
                "anywhere in the repository. Give it the directory its files live under."
            )
        malformed = [suffix for suffix in kind.suffixes if not suffix.startswith(".") or len(suffix) < 2]
        if not kind.suffixes or malformed:
            yield (
                f"Kind table: the row {kind.name!r} declares suffixes {list(kind.suffixes)}; each must "
                "be a file-name ending that starts with a dot, and there must be at least one."
            )


def _shared_paths(kinds: tuple[KindDeclaration, ...]) -> Iterator[str]:
    """Two rows whose roots can hold one file and whose suffixes cannot tell it apart.

    A longer suffix under a shared root is how an entity and its outgoing file are told apart, and is
    no contradiction; the *same* suffix is, because nothing then decides.
    """
    for one, other in combinations(kinds, 2):
        shared_roots = [
            ("/".join(a), "/".join(b)) for a in one.roots for b in other.roots if a and b and roots_overlap(a, b)
        ]
        shared_suffixes = sorted(set(one.suffixes) & set(other.suffixes))
        if shared_roots and shared_suffixes:
            a, b = shared_roots[0]
            yield (
                f"Kind table: the rows {one.name!r} and {other.name!r} both claim a file ending "
                f"{shared_suffixes[0]!r} under {a!r}" + (f" and {b!r}" if a != b else "") + ". "
                "A path holds one kind; give one of them a suffix or a root the other does not have."
            )


def _shared_id_prefixes(kinds: tuple[KindDeclaration, ...]) -> Iterator[str]:
    owners: dict[str, ArtifactKindName] = {}
    for kind in kinds:
        if kind.id_prefix is None:
            continue
        if not _ID_PREFIX.match(kind.id_prefix):
            yield (
                f"Kind table: the row {kind.name!r} declares the id prefix {kind.id_prefix!r}, which "
                f"no id can carry. A prefix matches {PREFIX_PATTERN}."
            )
        elif kind.id_prefix in owners and owners[kind.id_prefix] != kind.name:
            yield (
                f"Kind table: the rows {owners[kind.id_prefix]!r} and {kind.name!r} both declare the "
                f"id prefix {kind.id_prefix!r}. An id's prefix names one kind; change one of them."
            )
        else:
            owners[kind.id_prefix] = kind.name


def _impossible_facts(kinds: tuple[KindDeclaration, ...]) -> Iterator[str]:
    """Facts one row states that cannot both hold."""
    for kind in kinds:
        if kind.verification == "with-the-model" and not kind.moves_model_generation:
            yield (
                f"Kind table: the row {kind.name!r} is verified with the model and does not move the "
                "model generation. A verdict reached against the model is model state, and every "
                "read validated by the generation would outlive a change to it. Declare it "
                "`standalone` or `unverified`, or let it move the generation."
            )
