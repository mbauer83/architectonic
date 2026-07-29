"""Repository verification for Save commits.

Save commits stage the ENTIRE working tree, which may contain manually edited
files no tool ever validated — so both the engagement and the enterprise Save run
the artifact verifier first, and any blocking issue rejects the save with no
commit and no state change. This is the single exemption boundary: content-neutral
git operations (Submit's push of already-committed work, Discard's branch
cleanup) introduce no artifact content and are exempt from verification.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier_types import Severity


class SaveVerificationError(ValueError):
    """A Save commit was rejected because the working tree fails verification."""


def assert_repository_verifies(repo_root: Path) -> None:
    """Verify every artifact under *repo_root*; raise SaveVerificationError on errors."""
    from src.infrastructure.mcp.artifact_mcp.context import roots_key, verifier_for  # noqa: PLC0415

    verifier = verifier_for(roots_key([repo_root]), include_registry=True)
    results = verifier.verify_all(repo_root)
    failing = [result for result in results if not result.valid]
    if not failing:
        return
    lines = []
    for result in failing[:20]:
        for issue in result.issues:
            if issue.severity == Severity.ERROR:
                lines.append(f"{result.path}: {issue.code} {issue.message}")
    suffix = "" if len(failing) <= 20 else f" (+{len(failing) - 20} more files)"
    raise SaveVerificationError(
        "Save rejected — the working tree fails artifact verification; fix these before saving:\n"
        + "\n".join(lines[:40])
        + suffix
    )
