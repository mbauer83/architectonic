"""Shared write→verify→rollback commit step for admin (enterprise) writes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.verification.artifact_verifier import VerificationResult

from .types import WriteResult

VerificationDict = dict[str, object] | None
ToDict = Callable[[Path, VerificationResult], VerificationDict]


def dry_result(
    *, path: Path, artifact_id: str, content: str, verification: VerificationDict, warnings: list[str] | None = None
) -> WriteResult:
    return WriteResult(
        wrote=False, path=path, artifact_id=artifact_id, content=content,
        warnings=warnings or [], verification=verification,
    )


def commit_with_verification(
    *,
    path: Path,
    content: str,
    artifact_id: str,
    verify: Callable[[Path], VerificationResult],
    to_dict: ToDict,
    clear_repo_caches: Callable[[Path], None],
    warnings: list[str] | None = None,
) -> WriteResult:
    """Write *content*, verify, and on failure restore the prior file (or unlink a fresh one)."""
    warns = warnings or []
    prev = path.read_text(encoding="utf-8") if path.exists() else None
    path.write_text(content, encoding="utf-8")
    res = verify(path)
    if not res.valid:
        if prev is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(prev, encoding="utf-8")
        return WriteResult(
            wrote=False, path=path, artifact_id=artifact_id, content=content,
            warnings=warns, verification=to_dict(path, res),
        )
    clear_repo_caches(path)
    return WriteResult(
        wrote=True, path=path, artifact_id=artifact_id, content=None,
        warnings=warns, verification=to_dict(path, res),
    )
