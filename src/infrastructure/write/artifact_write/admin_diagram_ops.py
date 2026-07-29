"""Admin-mode diagram writes (enterprise repo). See admin_ops for the boundary contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier, VerificationResult
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS

from ._admin_commit import commit_with_verification, dry_result
from .boundary import assert_enterprise_write_root, modification_stamp
from .diagram_delete import _delete_diagram_core
from .types import WriteResult

__all__ = ["_write_diagram_to_enterprise", "admin_delete_diagram"]


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
    dry_run: bool,
) -> WriteResult:
    """Write a diagram PUML file into the enterprise repo's diagram-catalog."""
    assert_enterprise_write_root(repo_root)
    from src.application.modeling.artifact_write import format_diagram_puml  # noqa: PLC0415

    diagrams_dir = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    diagrams_dir.mkdir(parents=True, exist_ok=True)
    path = diagrams_dir / f"{artifact_id}.puml"
    content = format_diagram_puml(
        artifact_id=artifact_id, diagram_type=diagram_type, name=name, puml_body=puml,
        keywords=keywords, version=version, status=status, last_updated=modification_stamp(),
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
