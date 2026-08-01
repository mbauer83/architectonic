"""Document-collection path helpers shared by create/edit in ``document.py``.

Split out to keep ``document.py``'s CRUD/write-path functions the cohesive
unit; mirrors ``_diagram_group_move.py``'s equivalent for diagrams.
"""

from pathlib import Path

from src.application.artifacts.document_schema import get_document_schema, get_document_subdirectory
from src.application.repo_path_helpers import docs_root
from src.domain.repository.groups import UNCATEGORIZED


def _doc_dir(repo_root: Path, doc_subdirectory: str, group: str = UNCATEGORIZED) -> Path:
    base = docs_root(repo_root) / doc_subdirectory
    if group == UNCATEGORIZED:
        return base
    return base / group


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
