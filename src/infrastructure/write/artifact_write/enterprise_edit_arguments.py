"""What each edit function's arguments mean when the artifact turns out not to be ours to write.

An edit of enterprise-owned content is recorded as a change rather than written
(`enterprise_change_capture`). Deciding *that* is one rule; saying which of the caller's arguments
were actually given is three, because each edit function declares its own absence:

* an entity edit is absent as `_UNSET` for the fields whose value may legitimately be empty, and as
  `None` for the plain strings that have no way to be set to nothing;
* a document edit is absent as `None` throughout;
* a diagram edit needs three of its own, because `None` already means something there — clearing the
  viewpoint, clearing the edge labels, clearing the keyword list.

Collapsing those into one filter would make "not given" and "given as nothing" indistinguishable for
exactly the fields where the difference is the edit. So the three readings sit here, side by side,
where a change to one is visible against the others — rather than in the generic capture path, which
would have to know all three vocabularies to be right about any of them.

The diagram's sentinels are declared here for the same reason: the value and its meaning have one
owner between them. `edit_diagram` takes its defaults from here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.application.modeling.edit_field_catalogue import ArtifactKind
from src.infrastructure.write.artifact_write._entity_edit_support import _UNSET
from src.infrastructure.write.artifact_write.enterprise_change_capture import (
    recorded_instead_of_written,
)
from src.infrastructure.write.artifact_write.types import WriteResult

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

#: A diagram edit's own absences. `None` is not available for these three: it already says *clear it*.
KEYWORDS_UNSET: Any = ...
VIEWPOINT_UNSET = object()
EDGE_LABELS_UNSET = object()

#: What the rest of a diagram edit's arguments say when the caller did not mention them.
_PLAINLY_ABSENT = None

_DIAGRAM_ABSENT: dict[str, object] = {
    "keywords": KEYWORDS_UNSET,
    "viewpoint": VIEWPOINT_UNSET,
    "edge_labels": EDGE_LABELS_UNSET,
}


def entity_change(*, into: "Interception", **candidates: Any) -> WriteResult | None:
    """An entity edit recorded as a change, or None where the entity is this repository's own."""
    return into.recording(
        "entity", {n: v for n, v in candidates.items() if v is not _UNSET and v is not None}
    )


def document_change(*, into: "Interception", **candidates: Any) -> WriteResult | None:
    """A document edit recorded as a change, or None where the document is this repository's own."""
    return into.recording("document", {n: v for n, v in candidates.items() if v is not None})


def diagram_change(*, into: "Interception", **candidates: Any) -> WriteResult | None:
    """A diagram edit recorded as a change, or None where the diagram is this repository's own.

    Mechanics are never passed in: `rebuild_layout`, `replace_bindings` and the committed repository
    tell an applier how to behave, and a replay decides that for itself.
    """
    return into.recording(
        "diagram",
        {
            name: value
            for name, value in candidates.items()
            if value is not _DIAGRAM_ABSENT.get(name, _PLAINLY_ABSENT)
        },
    )


@dataclass(frozen=True, slots=True)
class Interception:
    """Where a recorded change would be written, as opposed to what it would say.

    The same seven collaborators for all three kinds, carried as one value so that the argument
    lists above are the *author's* fields and nothing else. Spelling the machinery out beside every
    field at three call sites is what pushed two edit modules past the source-length policy.
    """

    registry: "ArtifactRegistry | None"
    verifier: "ArtifactVerifier"
    clear_repo_caches: Callable[[Path], None]
    repo: "ArtifactRepository | None"
    repo_root: Path
    artifact_id: str
    dry_run: bool

    def recording(self, kind: ArtifactKind, fields: dict[str, Any]) -> WriteResult | None:
        return recorded_instead_of_written(
            kind=kind, registry=self.registry, verifier=self.verifier,
            clear_repo_caches=self.clear_repo_caches, repo=self.repo, repo_root=self.repo_root,
            artifact_id=self.artifact_id, fields=fields, dry_run=self.dry_run,
        )
