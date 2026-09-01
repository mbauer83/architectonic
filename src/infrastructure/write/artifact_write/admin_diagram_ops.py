"""Admin-mode diagram writes (enterprise repo). See admin_ops for the boundary contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier, VerificationResult
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS

from ._admin_commit import commit_with_verification, dry_result
from .boundary import ENTERPRISE, assert_enterprise_write_root, modification_stamp
from .diagram_delete import _delete_diagram_core
from .types import WriteResult

__all__ = ["_write_diagram_to_enterprise", "admin_delete_diagram", "admin_edit_diagram"]


def _diagram_verification(_path: Path, res: VerificationResult) -> dict[str, object]:
    return {
        "file_type": "diagram",
        "valid": res.valid,
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message} for i in res.issues
        ]
        if not res.valid
        else [],
    }


def _write_diagram_to_enterprise(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    diagram_type: str,
    name: str,
    puml: str,
    artifact_id: str,
    keywords: list[str] | None = None,
    version: str,
    status: str,
    entity_ids_used: list[str] | None = None,
    connection_ids_used: list[str] | None = None,
    dry_run: bool,
) -> WriteResult:
    """Write a diagram PUML file into the enterprise repo's diagram-catalog.

    ``entity_ids_used`` / ``connection_ids_used`` are what the body *draws*, recorded in the
    frontmatter. Not optional in practice, despite the signature: the verifier refuses a diagram whose
    body draws an alias listed in neither `entity-ids-used` nor `diagram-entities` (E315), and likewise
    a relation absent from `connection-ids-used` (E316). They defaulted to nothing and the caller had no
    way to supply them, so `POST /admin/api/diagrams` could not write a diagram over *any* entity
    selection: it answered 200 with `wrote: false` and three verification errors, every time. Nothing
    saw it because nothing had ever requested the operation — it was one of the seven entries
    `NEVER_REQUESTED_OPERATIONS` held for the admin surface.

    They stay optional-shaped rather than required because "the caller passed an empty selection" and
    "the caller had no way to say" are different, and it was the second that broke this.
    """
    assert_enterprise_write_root(repo_root)
    from src.application.modeling.artifact_write import format_diagram_puml  # noqa: PLC0415

    diagrams_dir = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    diagrams_dir.mkdir(parents=True, exist_ok=True)
    path = diagrams_dir / f"{artifact_id}.puml"
    content = format_diagram_puml(
        artifact_id=artifact_id, diagram_type=diagram_type, name=name, puml_body=puml,
        keywords=keywords, version=version, status=status, last_updated=modification_stamp(),
        entity_ids_used=entity_ids_used, connection_ids_used=connection_ids_used,
    )

    if dry_run:
        return dry_result(
            path=path, artifact_id=artifact_id, content=content,
            verification={"file_type": "diagram", "valid": True, "issues": []},
        )

    return commit_with_verification(
        path=path, content=content, artifact_id=artifact_id, verify=verifier.verify_diagram_file,
        to_dict=_diagram_verification, clear_repo_caches=clear_repo_caches,
    )


def admin_delete_diagram(
    *,
    repo_root: Path,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
) -> WriteResult:
    assert_enterprise_write_root(repo_root)
    return _delete_diagram_core(
        repo_root=repo_root, clear_repo_caches=clear_repo_caches, artifact_id=artifact_id, dry_run=dry_run
    )


def admin_edit_diagram(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    puml: str | None = None,
    name: str | None = None,
    keywords: list[str] | None = None,
    version: str | None = None,
    status: str | None = None,
    dry_run: bool,
) -> WriteResult:
    """Edit a diagram in the enterprise repository, composed from the engagement computation.

    `edit_diagram` never depended on which repository it was writing — every path it touches comes
    from the `repo_root` it is handed, and its one engagement-specific line was the root assertion,
    which is now a parameter. So this is that computation under the other authority rather than a
    second copy of it.

    The offered fields are the ones an enterprise diagram has: its body, its name, its keywords and
    its lifecycle. Not offered, each for a reason that is about this repository rather than about
    the computation — bindings, viewpoints and view derivations describe a diagram derived from a
    *live* model, which a promoted diagram is not; `group` is a relocation the admin surface cannot
    perform for any kind; and confidentiality is the assurance store's to decide, not an editor's.
    """
    from .diagram_edit import edit_diagram  # noqa: PLC0415

    return edit_diagram(
        authority=ENTERPRISE,
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        puml=puml,
        name=name,
        keywords=keywords,
        version=version,
        status=status,
        dry_run=dry_run,
    )
