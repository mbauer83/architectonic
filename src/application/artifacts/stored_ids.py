"""The ids a repository stores artifacts of one kind under, read from where the kind's row says its files are.

For a kind whose files are named by their id (`KindDeclaration.file_identity`) — a candidate architecture,
an icon. Whoever must know whether an id names a stored artifact of such a kind, and under which spelling
it is stored, asks here: the candidate store, the writer of a typed table's id cell, and the verifier of
one. The id is matched in its stable form (`canonical_entity_key`), so either spelling names it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.domain.artifact_id import canonical_entity_key
from src.domain.repository.artifact_location import ArtifactKindName, artifact_kind, source_globs

#: The id an artifact of a kind is stored under, for an id in either spelling; None where none is stored —
#: `stored_id` over one repository, as a writer or a verifier is handed it.
StoredIdOf = Callable[[ArtifactKindName, str], str | None]


def stored_ids(repo_root: Path, kind: ArtifactKindName) -> dict[str, str]:
    """The id each stored artifact of *kind* under *repo_root* carries, by its stable form."""
    declared = artifact_kind(kind)
    files = (path for pattern in source_globs(declared) for path in repo_root.glob(pattern))
    identities = (declared.file_identity(path) for path in files)
    return {canonical_entity_key(identity): identity for identity in identities}


def stored_id(repo_root: Path, kind: ArtifactKindName, spelled: str) -> str | None:
    """The id the artifact of *kind* that *spelled* names is stored under, in either spelling; None where none is."""
    return stored_ids(repo_root, kind).get(canonical_entity_key(spelled))


def stored_id_reader(repo_root: Path) -> StoredIdOf:
    """`stored_id` over *repo_root* for one verification or one edit: each kind's files are listed once, on
    its first ask, rather than once per cell — a typed table names many ids of the same kind."""
    listed: dict[ArtifactKindName, dict[str, str]] = {}

    def stored_id_of(kind: ArtifactKindName, spelled: str) -> str | None:
        ids = listed.get(kind)
        if ids is None:
            ids = listed[kind] = stored_ids(repo_root, kind)
        return ids.get(canonical_entity_key(spelled))

    return stored_id_of
