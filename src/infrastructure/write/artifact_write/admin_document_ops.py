"""Admin-mode document and diagram edits — the enterprise repository's other two artifact kinds.

There were none. An enterprise entity could be edited through the admin surface; an enterprise
document or diagram could be created by promotion, and after that only deleted. The enterprise
repository holds documents in practice — the shared standards a promotion puts there — so "edit the
thing you promoted" had no answer for two of the three kinds.

**Composed, not written again.** `edit_document` and `edit_diagram` never depended on which
repository they were writing: every path they touch is derived from a `repo_root` they are handed,
and the single engagement-specific line was the root assertion. That assertion is now a parameter —
`WriteAuthority` — so these are the same computation under the other authority rather than a second
copy of it. The second copy is what this stage exists to stop: the entity edit had one, and it had
silently lost two editable fields.

`group` is deliberately not offered. It is a relocation — for a document it moves the file between
`docs/<type>/<group>/` directories — and the admin surface can neither create into a group nor move
between them, for entities either. That gap is named where it is enforced and is not closed here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier

from .boundary import ENTERPRISE
from .document import edit_document
from .types import WriteResult

__all__ = ["admin_edit_document"]


def admin_edit_document(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    title: str | None = None,
    body: str | None = None,
    keywords: list[str] | None = None,
    extra_frontmatter: dict[str, object] | None = None,
    status: str | None = None,
    version: str | None = None,
    last_updated: str | None = None,
    dry_run: bool,
) -> WriteResult:
    """Edit a document in the enterprise repository, over the vocabulary an engagement edit has."""
    return edit_document(
        authority=ENTERPRISE,
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        title=title,
        body=body,
        keywords=keywords,
        extra_frontmatter=extra_frontmatter,
        status=status,
        version=version,
        last_updated=last_updated,
        dry_run=dry_run,
    )
