"""Document-collection path helpers shared by create/edit in ``document.py``.

Split out to keep ``document.py``'s CRUD/write-path functions the cohesive
unit; mirrors ``_diagram_group_move.py``'s equivalent for diagrams.
"""

from collections.abc import Callable
from pathlib import Path

from src.application.artifacts.document_schema import get_document_schema, get_document_subdirectory
from src.application.repo_path_helpers import docs_root
from src.application.repository_confinement import path_inside
from src.domain.repository.groups import UNCATEGORIZED

from ._entity_rename import rewrite_document_links_for_moved_artifact
from .file_transaction import FileChange, commit_file_changes


def _doc_dir(repo_root: Path, doc_subdirectory: str, group: str = UNCATEGORIZED) -> Path:
    base = path_inside(repo_root, docs_root(repo_root), doc_subdirectory)
    if group == UNCATEGORIZED:
        return base
    return path_inside(repo_root, base, group)


def _resolve_document_group_path(
    *, repo_root: Path, current_path: Path, doc_type: str, group: str | None
) -> Path:
    """Return the document path implied by re-homing to *group*.

    Returns *current_path* unchanged when ``group`` is None. Mirrors
    ``create_document``'s group-aware subdirectory selection so an edit-time
    move lands where a fresh create with that group would have.
    """
    if group is None:
        return current_path
    schema = get_document_schema(repo_root, doc_type)
    if schema is None:
        raise ValueError(f"Unknown doc-type: {doc_type!r}. No schema found at .arch-repo/documents/{doc_type}.json")
    doc_subdirectory = get_document_subdirectory(schema, doc_type)
    return _doc_dir(repo_root, doc_subdirectory, group) / current_path.name


def commit_document_move(
    *,
    repo_root: Path,
    old_path: Path,
    new_path: Path,
    content: str,
    group: str | None,
    clear_repo_caches: Callable[[Path], None],
) -> list[str]:
    """Write *content* at *new_path*, remove *old_path*, and follow every link to it; say what moved.

    Writing the new file and unlinking the old are one change: a crash between them leaves the
    document present in both groups, which parses and resolves cleanly and so is reported by
    nothing. *content* already reads from the new directory — the caller carried the document's own
    links across — so what is left is the other direction: whatever cites this document by path.
    """
    commit_file_changes(
        repo_root=repo_root,
        changes=[FileChange(path=new_path, content=content), FileChange(path=old_path, content=None)],
        rebuild_index=lambda: None,
        label="document-move",
    )
    clear_repo_caches(old_path)
    said = [f"Moved document to group '{group}': {new_path}"]
    for linking_path in rewrite_document_links_for_moved_artifact(
        repo_root=repo_root, old_path=old_path, new_path=new_path
    ):
        clear_repo_caches(linking_path)
        said.append(f"Updated document link in {linking_path.name}")
    return said
