"""Diagram deletion operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.candidate_repository import CandidateRepository
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_parsing import parse_frontmatter_from_path
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS, RENDERED
from src.domain.artifact_id import stable_id

from .boundary import assert_engagement_write_root
from .types import WriteResult


def _verification(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "diagram",
        "valid": True,
        "issues": [],
    }


def _find_diagram_file(repo_root: Path, artifact_id: str) -> Path | None:
    """Locate a diagram by its own id, scanning disk directly (no registry required).

    ``delete_diagram`` may run without a registry, unlike ``resolve_diagram_source_path``,
    so it cannot rely on ``find_file_by_id``'s canonicalization — an exact match wins;
    otherwise a short (rename-stable) id is accepted if exactly one file matches it
    (ambiguous short ids report not-found, same fail-safe convention as
    ``_MemStore.canonical_id``).
    """
    diagrams_root = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    if not diagrams_root.exists():
        return None
    short = stable_id(artifact_id)
    short_matches: list[Path] = []
    for suffix in ("*.puml", "*.md"):
        for path in sorted(diagrams_root.rglob(suffix)):
            if path.parent.name == RENDERED:
                continue
            fm = parse_frontmatter_from_path(path) or {}
            found_id = str(fm.get("artifact-id", ""))
            if found_id == artifact_id:
                return path
            if found_id and stable_id(found_id) == short:
                short_matches.append(path)
    return short_matches[0] if len(short_matches) == 1 else None


def _rendered_paths(diagram_path: Path) -> list[Path]:
    rendered_dir = diagram_path.parent.parent / RENDERED
    stem = diagram_path.stem
    candidates = {stem}
    parts = stem.split(".", 2)
    if len(parts) >= 3:
        candidates.add(parts[2])
    paths: list[Path] = []
    for name in candidates:
        paths.append(rendered_dir / f"{name}.png")
        paths.append(rendered_dir / f"{name}.svg")
    return paths


def _delete_diagram_core(
    *,
    repo_root: Path,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
    verifier: ArtifactVerifier | None = None,
    committed_repo: CandidateRepository | None = None,
) -> WriteResult:
    diagram_path = None
    if verifier is not None and verifier.registry is not None:
        diagram_path = verifier.registry.find_file_by_id(artifact_id)
    if diagram_path is None:
        diagram_path = _find_diagram_file(repo_root, artifact_id)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found in repo '{repo_root}'")

    rendered = [path for path in _rendered_paths(diagram_path) if path.exists()]
    warnings = [f"Will delete rendered artifact: {path.name}" for path in rendered]

    # E334 pre-flight: block deletion if hosted classifiers are still referenced by other diagrams.
    if committed_repo is not None and verifier is not None:
        from src.application.candidate_repository import candidate_with  # noqa: PLC0415
        from src.application.verification._verifier_contribution_runner import (  # noqa: PLC0415
            run_repository_contributions,
            workspace_types_from_catalogs,
        )
        _catalogs = getattr(verifier, "_catalogs", None)
        _ws = workspace_types_from_catalogs(_catalogs) if _catalogs is not None else {}
        _cand = candidate_with(committed_repo, deleted_ids=frozenset([artifact_id]), workspace_types=_ws)
        _rr = run_repository_contributions(
            candidate=_cand, committed=committed_repo, runtime_catalogs=_catalogs, repo_path=repo_root,
        )
        if _rr is not None and not _rr.valid:
            return WriteResult(
                wrote=False, path=diagram_path, artifact_id=artifact_id,
                content=None, warnings=warnings,
                verification={
                    "path": str(diagram_path), "file_type": "diagram", "valid": False,
                    "issues": [
                        {"severity": i.severity, "code": i.code, "message": i.message, "location": i.location}
                        for i in _rr.issues
                    ],
                },
            )

    if dry_run:
        preview = "\n".join(
            [
                f"Would delete diagram: {diagram_path}",
                *(f"Would delete rendered artifact: {path}" for path in rendered),
            ]
        )
        return WriteResult(
            wrote=False,
            path=diagram_path,
            artifact_id=artifact_id,
            content=preview,
            warnings=warnings,
            verification=_verification(diagram_path),
        )

    diagram_path.unlink(missing_ok=False)
    for path in rendered:
        path.unlink(missing_ok=True)
    clear_repo_caches(diagram_path)
    return WriteResult(
        wrote=True,
        path=diagram_path,
        artifact_id=artifact_id,
        content=None,
        warnings=warnings,
        verification=_verification(diagram_path),
    )


def delete_diagram(
    *,
    repo_root: Path,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
    verifier: ArtifactVerifier | None = None,
    committed_repo: CandidateRepository | None = None,
) -> WriteResult:
    assert_engagement_write_root(repo_root)
    return _delete_diagram_core(
        repo_root=repo_root,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
        verifier=verifier,
        committed_repo=committed_repo,
    )
