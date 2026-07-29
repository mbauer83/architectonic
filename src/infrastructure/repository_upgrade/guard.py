"""`--commit` safety guard for `arch-repair upgrade`: a backend currently serving the
target repo. This is the one thing that must block — two writers touching the same files —
so it fails closed whenever a responding backend's served roots can't be confirmed to
exclude the target, including backends that predate the `/api/backend-identity` endpoint.

Git status is deliberately *not* a gate here (see `arch_repair_upgrade`'s module docstring
for why): `conflicting_dirty_files` exists only to power an informational note about which
touched files already have uncommitted local edits, never to block `--commit`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.infrastructure.mutation_adapters.git import run_git


def dirty_worktree_files(repo_root: Path) -> list[str]:
    """Return every repo-relative path with uncommitted changes; empty if the tree is clean."""
    result = run_git(repo_root, ["status", "--porcelain"], timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"git status failed in {repo_root}: {result.stderr.strip()}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return [line[3:] for line in lines]


def conflicting_dirty_files(repo_root: Path, touched_locations: frozenset[str]) -> list[str]:
    """Return the subset of the dirty tree that this upgrade run would itself rewrite.

    Informational only — never gates `--commit`. *Unrelated* uncommitted work elsewhere in
    the repo (the common case) is excluded entirely, not just tolerated.
    """
    return [f for f in dirty_worktree_files(repo_root) if f in touched_locations]


@dataclass(frozen=True)
class BackendIdentity:
    repo_roots: tuple[str, ...]
    software_version: str


def probe_backend_identity(base_url: str, *, timeout_s: float = 1.0) -> BackendIdentity | None:
    """Query `GET /api/backend-identity`. Returns None on any failure (down, older backend, bad response)."""
    req = Request(
        f"{base_url.rstrip('/')}/api/backend-identity",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            if not (200 <= resp.status < 300):
                return None
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, URLError):
        return None
    roots = payload.get("repo_roots")
    version = payload.get("software_version")
    if not isinstance(roots, list) or not isinstance(version, str):
        return None
    return BackendIdentity(repo_roots=tuple(str(r) for r in roots), software_version=version)


@dataclass(frozen=True)
class BackendGuardResult:
    blocked: bool
    reason: str | None


def check_backend_not_serving(
    repo_root: Path,
    *,
    backend_responding: bool,
    identity: BackendIdentity | None,
) -> BackendGuardResult:
    """Fail closed: a responding backend whose served roots we can't confirm blocks --commit.

    `backend_responding=False` means nothing answered the liveness probe at all — that backend
    cannot be serving anything, so it never blocks.
    """
    if not backend_responding:
        return BackendGuardResult(blocked=False, reason=None)
    if identity is None:
        return BackendGuardResult(
            blocked=True,
            reason="A backend responded but has no /api/backend-identity endpoint (an older "
            "backend) — cannot confirm it isn't serving the target repo; refusing to commit.",
        )
    target = str(repo_root.resolve())
    served = {str(Path(r).resolve()) for r in identity.repo_roots}
    if target in served:
        return BackendGuardResult(
            blocked=True,
            reason=f"A running backend (v{identity.software_version}) is serving {target}; "
            "stop it before --commit.",
        )
    return BackendGuardResult(blocked=False, reason=None)
