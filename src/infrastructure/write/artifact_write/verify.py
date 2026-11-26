import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from src.application.artifacts.document_tables import ID_COLUMN_KINDS
from src.application.document_links import ArtifactPathOf, unresolved_id_links
from src.application.verification._verifier_document_tables import is_about_a_table_in_progress
from src.application.verification.artifact_verifier import ArtifactVerifier, VerificationResult
from src.application.verification.artifact_verifier_rules import unresolvable_id_link_issues
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationFileType
from src.config.repo_paths import ARCH_REPO, DIAGRAM_CATALOG, DIAGRAMS, DOCS, MODEL, PROJECTS
from src.domain.repository.artifact_location import artifact_kind
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.verification.verifier_factory import build_artifact_verifier


def refuses_a_document_write(issue: Issue) -> bool:
    """Whether *issue*, found in a document about to be written, keeps it from being written.

    * an error always refuses;
    * an unresolvable link (W155) always refuses — a path to no file, or a link written with an
      artifact id that names no artifact. The owner decided the second: a document is not written
      leaving a link to nothing, and the finding names the link;
    * a typed table still being filled in does not refuse, which is the state every such table is in
      until its last row is complete;
    * every other warning refuses, as it did before any of the above was stated. Which of them a
      document may be written with has not been decided, so none is let through by default.
    """
    match issue:
        case Issue(severity=Severity.ERROR) | Issue(code="W155"):
            return True
        case _:
            return not is_about_a_table_in_progress(issue)


def document_write_allowed(res: VerificationResult) -> bool:
    """Whether a document that verifies as *res* may be written. The one decision every document write asks."""
    return not any(refuses_a_document_write(issue) for issue in res.issues)


def verify_document_write(
    *,
    verifier: ArtifactVerifier,
    desired_name: str,
    content: str,
    repo_root: Path,
    written_to: Path,
    path_of: ArtifactPathOf,
) -> VerificationResult:
    """Verify *content* as the document a write would leave at *desired_name* under `docs/`.

    The verifier is not given the repository's ids, so a link written with one that names nothing is
    asked of the write's own resolver over the whole content — a part the write did not address is
    left by it all the same — and reported as the verifier reports a path to no file.
    """
    res = verify_content_in_temp_path(
        verifier=verifier, file_type="document", desired_name=desired_name, content=content,
        support_repo_root=repo_root,
    )
    unresolved = unresolved_id_links(content, written_to=written_to, path_of=path_of)
    res.issues.extend(unresolvable_id_link_issues(unresolved, str(res.path)))
    return res


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


#: Where the artifacts an `id` column names are stored: the top directory of each such kind's roots.
_ID_COLUMN_ROOTS = tuple(dict.fromkeys(root[0] for kind in ID_COLUMN_KINDS for root in artifact_kind(kind).roots))


def _document_temp_path(tmp_root: Path, desired_name: str, support_repo_root: Path | None) -> Path:
    """Mirror the docs tree (symlinks) around the document under test so cross-doc checks resolve.

    The diagram catalog is mirrored for the same reason the model is: a document's prose may point
    at a diagram, and a document type may now *require* that it does. Without it the link rule
    resolved every `.puml` href against a tree that has no diagrams in it and reported each one as
    unresolvable, refusing a write the real repository would have accepted. So is every kind an `id`
    column may name (`ID_COLUMN_KINDS`): an adaptation naming a stored candidate was refused as naming
    none, because the temp tree held no candidates.
    """
    tmp_path = tmp_root / DOCS / desired_name
    if support_repo_root is None:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        return tmp_path

    for top in (ARCH_REPO, MODEL, PROJECTS, DIAGRAM_CATALOG, *_ID_COLUMN_ROOTS):
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


def _beside_nothing(tmp_root: Path, desired_name: str, _support_repo_root: Path | None) -> Path:
    """A file whose checks read nothing around it, at the top of the temp tree."""
    return tmp_root / desired_name


#: Where in a temp tree a file of each kind is laid out, so the checks that read around it find what
#: they would in the repository. One entry per verified kind.
_TEMP_LAYOUTS: Mapping[VerificationFileType, Callable[[Path, str, Path | None], Path]] = {
    "candidate-architecture": _beside_nothing,
    "entity": _beside_nothing,
    "connection": _beside_nothing,
    "icon": _beside_nothing,
    "diagram": _diagram_temp_path,
    "document": _document_temp_path,
}


def verify_content_in_temp_path(
    *,
    verifier: ArtifactVerifier,
    file_type: VerificationFileType,
    desired_name: str,
    content: str,
    support_repo_root: Path | None = None,
    verify_fn: Callable[[Path], VerificationResult] | None = None,
) -> VerificationResult:
    """Verify *content* by writing it to a temp location laid out for its file type.

    The file is verified by the verifier bound to *file_type*, unless ``verify_fn`` says otherwise.
    An entity's writers pass one to name the repository whose ``.arch-repo/schemata`` govern it: the
    temp file lives outside every repo root, so without it the frontmatter- and attribute-schema checks
    would be skipped in the preview, under-reporting relative to the real write. A matrix diagram's
    writers pass one because its layout is a diagram's and its verifier is the matrix one.
    """
    tmp_root = Path(tempfile.mkdtemp(prefix=f"model-write-verify-{file_type}-"))
    tmp_path = _TEMP_LAYOUTS[file_type](tmp_root, desired_name, support_repo_root)
    tmp_path.write_text(content, encoding="utf-8")
    if verify_fn is not None:
        return verify_fn(tmp_path)
    return verifier.verify_as(file_type, tmp_path)


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
