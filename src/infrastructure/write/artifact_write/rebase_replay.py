"""Reading and re-applying a recorded edit inside a rehearsal worktree.

`rebase_rehearsal` drives the rehearsal and `change_rebase` decides where each change stands; both
take the two capabilities they cannot have — reading the current artifact and attempting the replay —
as injected functions. This supplies them, and until it existed the rehearsal had no production
caller at all: the machinery was written, tested against stubs, and reachable from nothing.

**The replay is the write call itself.** That is the whole reason a change records a semantic edit
rather than a patch: re-applying it and letting the verifier answer is the only honest test of
whether it still applies. So this calls the same three write functions an author's edit calls, at the
worktree root — where a temp path infers as an engagement, so the ordinary guard passes and the
enterprise one would not, and where nothing is watching.

`repo=None` on purpose: a replay must *write*, not record a change about writing. Passing a
repository would send it straight back through the interception it is rehearsing the output of.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.application.modeling.proposal_edit import ProposalEdit
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.types import WriteResult

logger = logging.getLogger(__name__)


class Rehearser:
    """The two capabilities a rehearsal needs, over one index of one worktree.

    One index, opened once and closed with the block: the rehearsal reads and writes the same
    checkout repeatedly, and an index per call would open a connection pool per question.
    """

    def __init__(self, worktree: Path) -> None:
        self._worktree = worktree
        self._index = shared_artifact_index(worktree)
        self._index.refresh()

    def read_current(self, _worktree: Path, artifact_id: str) -> EntityRecord | DocumentRecord | None:
        """The artifact as this worktree has it, or None where it is not there any more."""
        return self._index.get_entity(artifact_id) or self._index.get_document(artifact_id)

    def apply_edit(self, worktree: Path, edit: ProposalEdit) -> str | None:
        """Make the edit here. Returns the refusal to show an author, or None where it applied."""
        try:
            result = self._write(worktree, edit)
        except (ValueError, OSError) as refused:
            return str(refused)
        self._index.refresh()
        return None if result.wrote else _refusal_of(result)

    def close(self) -> None:
        self._index.close()

    def _write(self, worktree: Path, edit: ProposalEdit) -> WriteResult:
        from src.infrastructure.write.artifact_write.boundary import (  # noqa: PLC0415
            assert_engagement_write_root,
        )
        from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram  # noqa: PLC0415
        from src.infrastructure.write.artifact_write.document import edit_document  # noqa: PLC0415
        from src.infrastructure.write.artifact_write.entity_edit import edit_entity  # noqa: PLC0415

        registry = ArtifactRegistry(self._index)
        verifier = build_artifact_verifier(registry, catalogs=process_runtime_catalogs())
        refresh: Callable[[Path], None] = lambda _path: self._index.refresh()  # noqa: E731

        # Spelled out per kind rather than through a shared mapping of arguments: the three write
        # functions do not take the same ones, and a mapping splatted into all three is a claim the
        # type checker cannot check and the reader cannot follow.
        match edit.kind:
            case "document":
                return edit_document(
                    assert_write_root=assert_engagement_write_root,
                    repo_root=worktree, verifier=verifier, clear_repo_caches=refresh,
                    artifact_id=edit.artifact_id, registry=registry, repo=None, dry_run=False,
                    **_document_arguments(edit),
                )
            case "diagram":
                return edit_diagram(
                    assert_write_root=assert_engagement_write_root,
                    repo_root=worktree, verifier=verifier, clear_repo_caches=refresh,
                    artifact_id=edit.artifact_id, repo=None, dry_run=False,
                    **edit.fields,
                )
            case _:
                return edit_entity(
                    repo_root=worktree, registry=registry, verifier=verifier,
                    clear_repo_caches=refresh, artifact_id=edit.artifact_id, repo=None,
                    dry_run=False, **edit.fields,
                )


@contextmanager
def rehearser_for(worktree: Path) -> Iterator[Rehearser]:
    """A rehearser over `worktree`, whose index is closed however the block ends."""
    rehearser = Rehearser(worktree)
    try:
        yield rehearser
    finally:
        rehearser.close()


def _document_arguments(edit: ProposalEdit) -> dict[str, Any]:
    """A document edit takes every content field by name, absent ones as None.

    Unlike the entity and diagram edits, which default theirs. Spelled here rather than at the call
    site so the difference is stated once, where the vocabulary it belongs to is.
    """
    named = ("title", "body", "keywords", "extra_frontmatter", "status", "version", "last_updated")
    return {name: edit.fields.get(name) for name in named} | {
        name: value for name, value in edit.fields.items() if name not in named
    }


def _refusal_of(result: WriteResult) -> str:
    """The verifier's own words, or the warning that stood in for them."""
    issues: list[Any] = (result.verification or {}).get("issues") or []
    if issues:
        return "; ".join(f"{issue['code']}: {issue['message']}" for issue in issues)
    return "; ".join(result.warnings) or "the write was refused without saying why"
