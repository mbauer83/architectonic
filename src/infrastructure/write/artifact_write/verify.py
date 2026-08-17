import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from src.application.verification.artifact_verifier import ArtifactVerifier, VerificationResult
from src.config.repo_paths import ARCH_REPO, DIAGRAM_CATALOG, DIAGRAMS, DOCS, MODEL, PROJECTS
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.verification.verifier_factory import build_artifact_verifier


def _diagram_temp_path(tmp_root: Path, desired_name: str, support_repo_root: Path | None) -> Path:
    """Lay out a minimal diagram-catalog so relative includes resolve during PlantUML checks."""
    cat = tmp_root / DIAGRAM_CATALOG
    diagrams = cat / DIAGRAMS
    diagrams.mkdir(parents=True, exist_ok=True)
    if support_repo_root is not None:
        for support in ("_archimate-stereotypes.puml", "_archimate-glyphs.puml"):
            src = support_repo_root / DIAGRAM_CATALOG / support
            if src.exists():
                (cat / support).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return diagrams / desired_name


def _mirror_doc_entry(existing: Path, source_root: Path, mirror_root: Path, skip_rel: Path) -> None:
    """Recreate one docs-tree entry under *mirror_root*: dirs as real dirs, files as symlinks."""
    rel = existing.relative_to(source_root)
    target = mirror_root / rel
    if existing.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    elif rel != skip_rel:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(existing, target)


def _document_temp_path(tmp_root: Path, desired_name: str, support_repo_root: Path | None) -> Path:
    """Mirror the docs tree (symlinks) around the document under test so cross-doc checks resolve.

    The diagram catalog is mirrored for the same reason the model is: a document's prose may point
    at a diagram, and a document type may now *require* that it does. Without it the link rule
    resolved every `.puml` href against a tree that has no diagrams in it and reported each one as
    unresolvable, refusing a write the real repository would have accepted.
    """
    tmp_path = tmp_root / DOCS / desired_name
    if support_repo_root is None:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        return tmp_path

    for top in (ARCH_REPO, MODEL, PROJECTS, DIAGRAM_CATALOG):
        src = support_repo_root / top
        if src.exists():
            os.symlink(src, tmp_root / top, target_is_directory=True)

    source_docs_root = support_repo_root / DOCS
    mirrored_docs_root = tmp_root / DOCS
    mirrored_docs_root.mkdir(parents=True, exist_ok=True)
    skip_rel = Path(desired_name)
    for existing in source_docs_root.rglob("*") if source_docs_root.exists() else []:
        _mirror_doc_entry(existing, source_docs_root, mirrored_docs_root, skip_rel)
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    return tmp_path


def verify_content_in_temp_path(
    *,
    verifier: ArtifactVerifier,
    file_type: Literal["entity", "connection", "diagram", "document"],
    desired_name: str,
    content: str,
    support_repo_root: Path | None = None,
    schema_repo_root: Path | None = None,
    verify_fn: Callable[[Path], VerificationResult] | None = None,
) -> VerificationResult:
    """Verify *content* by writing it to a temp location laid out for its file type.

    ``verify_fn`` overrides the file-type's default verifier method — e.g. matrix
    diagrams share ``file_type="diagram"``'s temp layout but need
    ``verify_matrix_diagram_file`` instead of the PUML-oriented ``verify_diagram_file``.

    ``schema_repo_root`` names the repo whose ``.arch-repo/schemata`` govern the content:
    the temp file lives outside every repo root, so without it the entity frontmatter- and
    attribute-schema checks (which resolve schemata relative to the governing repo) would be
    silently skipped in the dry-run preview — under-reporting relative to the real write.
    """
    tmp_root = Path(tempfile.mkdtemp(prefix=f"model-write-verify-{file_type}-"))
    if file_type == "diagram":
        tmp_path = _diagram_temp_path(tmp_root, desired_name, support_repo_root)
    elif file_type == "document":
        tmp_path = _document_temp_path(tmp_root, desired_name, support_repo_root)
    else:
        tmp_path = tmp_root / desired_name

    tmp_path.write_text(content, encoding="utf-8")

    if verify_fn is not None:
        return verify_fn(tmp_path)

    if file_type == "entity":
        return verifier.verify_entity_file(tmp_path, schema_repo_root=schema_repo_root)

    dispatch = {
        "connection": verifier.verify_connection_file,
        "document": verifier.verify_document_file,
        "diagram": verifier.verify_diagram_file,
    }
    return dispatch[file_type](tmp_path)


def collect_verification_errors(repo_root: Path, *, include_diagrams: bool = False) -> list[str]:
    """Build a verifier for *repo_root* and return formatted ``CODE: message (location)`` error strings."""
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry  # noqa: PLC0415
    from src.infrastructure.artifact_index import shared_artifact_index  # noqa: PLC0415

    store = shared_artifact_index(repo_root)
    registry = ArtifactRegistry(store)
    committed_repo = committed_repository(store)
    verifier = build_artifact_verifier(
        registry,
        catalogs=process_runtime_catalogs(),
        committed_repo=committed_repo,
    )
    return [
        f"{i.code}: {i.message} ({i.location})"
        for r in verifier.verify_all(repo_root, include_diagrams=include_diagrams)
        for i in r.issues
        if i.severity == "error"
    ]
