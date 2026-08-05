"""Which stored architecture references a rename speaks about.

An assurance node's reference to an architecture artifact holds the artifact's full id, whose slug
tail is a readability hint — identity is the `PREFIX@epoch.random` stem, and every consumer resolves
through it (`canonical_entity_key`). So a rename never breaks a reference; it makes one *misleading*,
which matters most here, where the reader is reviewing a safety argument and the name is all they see.

Matching is on the stem rather than on the id being renamed *from*, exactly as the architecture
repository's own referrer rewrites do: a reference left holding some third, older slug is then found
and healed too, rather than being unreachable by every later rename.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from src.domain.artifact_id import stable_id


def refs_to_retarget(
    refs: Iterable[Mapping[str, object]], *, new_arch_artifact_id: str
) -> tuple[dict[str, object], ...]:
    """The refs whose `arch_artifact_id` names the same artifact under a different spelling."""
    stem = stable_id(new_arch_artifact_id)
    return tuple(
        dict(ref)
        for ref in refs
        if (current := str(ref.get("arch_artifact_id", ""))) != new_arch_artifact_id
        and stable_id(current) == stem
    )
