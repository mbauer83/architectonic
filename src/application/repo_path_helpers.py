"""Path-semantics helpers for the architecture repository.

All layout assumptions are centralised here. Every component that needs to
derive a path or classify a file should call these helpers rather than
hard-coding the directory structure.

Supports both the **legacy** flat layout and the **target** group-aware layout
transitionally (T1.3):

  Legacy  : model/<domain>/<type>/…
            diagram-catalog/diagrams/<file>
            docs/<doc-type>/<file>

  Target  : projects/<slug>/model/<domain>/<type>/…
            diagram-catalog/diagrams/<collection>/<file>
            docs/<doc-type>/<collection>/<file>

The group_fn derivation is the key primitive that the indexer uses to populate
the ``group`` field on every record.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.domain.repository.groups import UNCATEGORIZED
from src.domain.repository.repo_layout import DIAGRAM_CATALOG, DIAGRAMS, DOCS, MODEL, RENDERED

_PROJECTS = "projects"

# ---------------------------------------------------------------------------
# Root derivation
# ---------------------------------------------------------------------------


def model_root_legacy(repo_root: Path) -> Path:
    """Legacy model root: <repo>/model/"""
    return repo_root / MODEL


def all_model_roots(repo_root: Path) -> list[Path]:
    """All model roots — legacy root plus every projects/<slug>/model/ directory.

    Returns existing paths only so callers can iterate without existence checks.
    """
    roots: list[Path] = []
    legacy = repo_root / MODEL
    if legacy.exists():
        roots.append(legacy)
    projects_dir = repo_root / _PROJECTS
    if projects_dir.exists():
        for slug_dir in sorted(projects_dir.iterdir()):
            if slug_dir.is_dir():
                model_dir = slug_dir / MODEL
                if model_dir.exists():
                    roots.append(model_dir)
    return roots


def diagram_source_root(repo_root: Path) -> Path:
    """Diagram source root: <repo>/diagram-catalog/diagrams/"""
    return repo_root / DIAGRAM_CATALOG / DIAGRAMS


def resolve_diagram_source_path(
    repo_root: Path,
    artifact_id: str,
    find_file_by_id: Callable[[str], Path | None] | None = None,
) -> Path | None:
    """Resolve a diagram's source ``.puml``, honouring group-collection subdirectories.

    Single resolution seam for every read/write process: the conventional flat path is tried
    first (fast, no index dependency), then the injected id→path resolver (the artifact index)
    so a diagram in a group collection — or any other subdirectory — resolves wherever it
    actually lives rather than 404'ing against an assumed flat layout. The resolver is passed
    as a callable to keep this path helper free of any index/port dependency.
    """
    flat = diagram_source_root(repo_root) / f"{artifact_id}.puml"
    if flat.exists():
        return flat
    if find_file_by_id is not None:
        resolved = find_file_by_id(artifact_id)
        if resolved is not None and resolved.exists():
            return resolved
    return None


# Confidential diagram sources (e.g. assurance diagrams classified above the publishability
# ceiling) live under this subdirectory of the scanned source root. It is still indexed
# (the source scan recurses), so reads/listing/GUI work, but a `.gitignore` written into it
# keeps its contents out of git so confidential analysis content never reaches a shared repo.
CONFIDENTIAL_DIAGRAMS = "confidential"


def diagram_source_confidential_root(repo_root: Path) -> Path:
    """Confidential diagram source root: <repo>/diagram-catalog/diagrams/confidential/"""
    return diagram_source_root(repo_root) / CONFIDENTIAL_DIAGRAMS


def rendered_root(repo_root: Path) -> Path:
    """Rendered output root: <repo>/diagram-catalog/rendered/"""
    return repo_root / DIAGRAM_CATALOG / RENDERED


def docs_root(repo_root: Path) -> Path:
    """Document root: <repo>/docs/"""
    return repo_root / DOCS


# ---------------------------------------------------------------------------
# Rendered-path derivation
# ---------------------------------------------------------------------------


def rendered_dir_for_diagram(diagram_path: Path, repo_root: Path) -> Path:
    """Return the rendered output directory for a diagram source file.

    Legacy  : diagrams/<file>       → rendered/
    Target  : diagrams/<coll>/<file> → rendered/<coll>/
    """
    src_root = diagram_source_root(repo_root)
    try:
        rel = diagram_path.resolve().relative_to(src_root.resolve())
    except ValueError:
        # Not under the expected diagrams root — fall back to sibling rendered/
        return diagram_path.parent.parent / RENDERED

    parts = rel.parts
    if len(parts) <= 1:
        # Legacy: file directly inside diagrams/
        return rendered_root(repo_root)
    # Target: first segment is the collection
    return rendered_root(repo_root) / parts[0]


def rendered_path_for(diagram_path: Path, repo_root: Path, suffix: str = ".png") -> Path:
    """Full rendered output path for a diagram file.

    E.g. diagrams/landing-zone/DIAG@xxx.puml → rendered/landing-zone/DIAG@xxx.png
    """
    out_dir = rendered_dir_for_diagram(diagram_path, repo_root)
    return out_dir / (diagram_path.stem + suffix)


# ---------------------------------------------------------------------------
# Repo-root derivation from an artifact path
# ---------------------------------------------------------------------------


def repo_root_for_diagram_path(diagram_path: Path) -> Path | None:
    """Derive repo root from a diagram source path by walking up to find diagram-catalog/.

    Returns None if the path is not under any diagram-catalog/.
    """
    p = diagram_path.resolve()
    for parent in p.parents:
        if (parent / DIAGRAM_CATALOG).exists():
            return parent
    return None


def repo_root_for_model_path(model_path: Path) -> Path | None:
    """Derive repo root from a model-file path.

    Handles both legacy (model/<domain>/…) and target (projects/<slug>/model/…).
    """
    p = model_path.resolve()
    parts = p.parts
    # Look for /model/ segment (the last occurrence)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == MODEL:
            candidate = Path(*parts[:i])
            # Target layout: projects/<slug>/model → root is two levels above
            if i >= 2 and parts[i - 1] != _PROJECTS and i >= 1:
                parent = Path(*parts[: i - 1])
                if parts[i - 1] != _PROJECTS and (parent / _PROJECTS).exists():
                    return parent
            return candidate
    return None


# ---------------------------------------------------------------------------
# group_fn — family-aware group derivation from path
# ---------------------------------------------------------------------------


def group_fn_entity(entity_path: Path, repo_root: Path) -> str:
    """Derive the model-project group slug from an entity (or connection) file path.

    Legacy  : model/<domain>/<type>/<file>     → "uncategorized"
    Target  : projects/<slug>/model/…/<file>   → slug
    """
    try:
        rel = entity_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return UNCATEGORIZED

    parts = rel.parts
    if not parts:
        return UNCATEGORIZED

    # Target layout: projects/<slug>/model/…
    if parts[0] == _PROJECTS and len(parts) >= 3 and parts[2] == MODEL:
        return parts[1]

    return UNCATEGORIZED


def group_fn_diagram(diagram_path: Path, repo_root: Path) -> str:
    """Derive the diagram-collection group slug from a diagram source path.

    Legacy  : diagram-catalog/diagrams/<file>                          → "uncategorized"
    Target  : diagram-catalog/diagrams/<collection>/<file>             → collection
    Confidential : diagram-catalog/diagrams/confidential/<collection>/<file> → collection
    """
    src_root = diagram_source_root(repo_root)
    try:
        rel = diagram_path.resolve().relative_to(src_root.resolve())
    except ValueError:
        return UNCATEGORIZED

    parts = rel.parts
    if parts and parts[0] == CONFIDENTIAL_DIAGRAMS:
        return parts[1] if len(parts) >= 3 else UNCATEGORIZED
    if len(parts) >= 2:
        return parts[0]  # collection segment
    return UNCATEGORIZED


def group_fn_document(doc_path: Path, repo_root: Path) -> str:
    """Derive the document-collection group slug from a document path.

    doc-type subdir is determined by the first segment under docs/.
    Legacy  : docs/<doc-type>/<file>                    → "uncategorized"
    Target  : docs/<doc-type>/<collection>/<file>       → collection
    """
    docs = docs_root(repo_root)
    try:
        rel = doc_path.resolve().relative_to(docs.resolve())
    except ValueError:
        return UNCATEGORIZED

    parts = rel.parts
    # parts[0] = doc-type-subdir, parts[1] (if present) = file or collection, parts[2] = file
    if len(parts) >= 3:
        return parts[1]  # collection segment
    return UNCATEGORIZED


def group_fn(path: Path, repo_root: Path) -> str:
    """Family-aware group derivation — dispatches to the right family helper.

    Uses path structure to determine the family. Falls back to UNCATEGORIZED
    when the path cannot be classified.
    """
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return UNCATEGORIZED

    parts = rel.parts
    if not parts:
        return UNCATEGORIZED

    # Entity/connection: under model/ (legacy) or projects/<slug>/model/ (target)
    if parts[0] == MODEL or parts[0] == _PROJECTS:
        return group_fn_entity(path, repo_root)

    # Diagram: under diagram-catalog/
    if parts[0] == DIAGRAM_CATALOG:
        return group_fn_diagram(path, repo_root)

    # Document: under docs/
    if parts[0] == DOCS:
        return group_fn_document(path, repo_root)

    return UNCATEGORIZED


# ---------------------------------------------------------------------------
# Include-base resolution
# ---------------------------------------------------------------------------


def diagram_include_base(repo_root: Path) -> Path:
    """Return the directory that !include paths resolve relative to.

    The shared _archimate-*.puml files live at the diagram-catalog root,
    so includes resolve relative to that directory.
    """
    return repo_root / DIAGRAM_CATALOG


# ---------------------------------------------------------------------------
# Document-link helpers (§4.6)
# ---------------------------------------------------------------------------


def rewrite_doc_link(
    link_target: str,
    *,
    doc_old_dir: Path,
    doc_new_dir: Path,
    target_old_path: Path,
    target_new_path: Path,
) -> str:
    """Rewrite a relative document link after a path move.

    Computes the new relative path from doc_new_dir to target_new_path,
    preserving the link text while updating only the href.

    Returns the rewritten link or the original if it does not match
    target_old_path when resolved from doc_old_dir.
    """
    import posixpath

    try:
        resolved = (doc_old_dir / link_target).resolve()
        if resolved != target_old_path.resolve():
            return link_target
    except OSError:
        return link_target

    # Compute new relative path
    try:
        new_rel = posixpath.relpath(
            target_new_path.resolve().as_posix(),
            doc_new_dir.resolve().as_posix(),
        )
    except ValueError:
        return link_target

    return new_rel
