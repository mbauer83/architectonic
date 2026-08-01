"""Scaffold a new engagement repository with baseline schemata and document types."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from src.application.artifacts.document_schema import get_document_subdirectory
from src.config.repo_paths import ARCH_DOC_SCHEMATA, ARCH_REPO, DIAGRAM_CATALOG, DIAGRAMS, DOCS, MODEL, RENDERED
from src.domain.repository.repo_default_schemata import (
    BASE_DOCUMENT_SCHEMAS,
    DEFAULT_SCHEMATA,
)
from src.infrastructure.workspace._assurance_doc_types import ASSURANCE_DOCUMENT_SCHEMAS

INITIAL_COMMIT_MESSAGE = "Initialize engagement architecture repository"

# Base doc-types (adr/spec/standard) are scaffolded into every repo. Assurance doc-types are
# added on top for empty-repo init (current default); the repair path writes the base set only,
# so an existing non-assurance repo is not retrofitted with assurance doc-types.
DEFAULT_DOCUMENT_SCHEMAS: dict[str, dict] = {**BASE_DOCUMENT_SCHEMAS, **ASSURANCE_DOCUMENT_SCHEMAS}



def _write_json_if_missing(path: Path, payload: dict) -> None:
    if path.exists():
        return
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


_ARCH_REPO_CONFIG_TEMPLATE = """\
# Repository authoring policy.
# required_defaults_policy: strict  — every required attribute must declare a valid default
# required_defaults_policy: non-strict  — recommended but not enforced at startup
required_defaults_policy: non-strict
"""


def _write_arch_repo_config_if_missing(arch_repo_dir: Path) -> None:
    config_path = arch_repo_dir / "config.yaml"
    if config_path.exists():
        return
    config_path.write_text(_ARCH_REPO_CONFIG_TEMPLATE, encoding="utf-8")


def _migrate_legacy_flat_schemata(arch_repo_dir: Path, schemata_dir: Path) -> list[str]:
    """Remove legacy schema files written flat in .arch-repo/, migrating canonical ones first.

    Older repos placed schema files directly under .arch-repo/, where the loader (which reads
    only .arch-repo/schemata/) ignores them. A flat file whose name is a canonical schema is
    moved into schemata/ when not already present; non-canonical legacy files (e.g. the old
    mis-pluralised `frontmatter.entities.schema.json`) are simply dropped. The canonical files
    have already been written to schemata/ by the caller, so this never loses real content.
    Returns the names of the flat files that were migrated or dropped.
    """
    removed: list[str] = []
    for flat in sorted(arch_repo_dir.glob("*.schema.json")):
        if not flat.is_file():
            continue
        canonical = schemata_dir / flat.name
        if flat.name in DEFAULT_SCHEMATA and not canonical.exists():
            canonical.write_text(flat.read_text(encoding="utf-8"), encoding="utf-8")
        flat.unlink()
        removed.append(flat.name)
    return removed


def ensure_arch_repo_defaults(
    path: Path,
    *,
    document_schemas: dict[str, dict] = BASE_DOCUMENT_SCHEMAS,
) -> dict[str, list[str]]:
    """Idempotently bring an existing repo's .arch-repo up to current defaults (no git).

    Writes any missing doc-type schemas (`.arch-repo/documents/`), attribute + frontmatter
    schemata (`.arch-repo/schemata/`), and `config.yaml`, and migrates legacy flat schema files
    into `schemata/`. Existing files are never overwritten, so an operator's local edits are
    preserved. Returns a summary of what was added/migrated for reporting.
    """
    arch_repo_dir = path / ARCH_REPO
    documents_dir = arch_repo_dir / ARCH_DOC_SCHEMATA
    schemata_dir = arch_repo_dir / "schemata"
    documents_dir.mkdir(parents=True, exist_ok=True)
    schemata_dir.mkdir(parents=True, exist_ok=True)

    added_docs: list[str] = []
    for doc_type, schema in document_schemas.items():
        target = documents_dir / f"{doc_type}.json"
        if not target.exists():
            _write_json_if_missing(target, schema)
            added_docs.append(f"{doc_type}.json")
        (path / DOCS / get_document_subdirectory(schema, doc_type)).mkdir(parents=True, exist_ok=True)

    added_schemata: list[str] = []
    for filename, schema in DEFAULT_SCHEMATA.items():
        target = schemata_dir / filename
        if not target.exists():
            _write_json_if_missing(target, schema)
            added_schemata.append(filename)

    migrated = _migrate_legacy_flat_schemata(arch_repo_dir, schemata_dir)
    config_added = not (arch_repo_dir / "config.yaml").exists()
    _write_arch_repo_config_if_missing(arch_repo_dir)

    return {
        "documents": added_docs,
        "schemata": added_schemata,
        "migrated_flat": migrated,
        "config": ["config.yaml"] if config_added else [],
    }


def _run_git(args: list[str], cwd: Path) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise SystemExit(f"ERROR: git {' '.join(args)} failed for {cwd}\n{result.stderr.strip()}")


def _git_output(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _has_commits(path: Path) -> bool:
    return _git_output(["rev-parse", "--verify", "HEAD"], cwd=path).returncode == 0


def _ensure_git_repo(path: Path, *, git_url: str | None, branch: str) -> None:
    git_dir = path / ".git"
    if not git_dir.exists():
        _run_git(["init", "-b", branch], cwd=path)
    if git_url is None:
        return

    result = _git_output(["remote", "get-url", "origin"], cwd=path)
    if result.returncode != 0:
        _run_git(["remote", "add", "origin", git_url], cwd=path)
        return
    current = result.stdout.strip()
    if current != git_url:
        raise SystemExit(f"ERROR: {path} already has origin={current!r}, expected {git_url!r}")
def _commit_initial_scaffold(path: Path, *, commit_author_name: str, commit_author_email: str) -> None:
    if _has_commits(path):
        return
    _run_git(["add", "-A"], cwd=path)
    result = _git_output(
        [
            "-c",
            f"user.name={commit_author_name}",
            "-c",
            f"user.email={commit_author_email}",
            "commit",
            "-m",
            INITIAL_COMMIT_MESSAGE,
        ],
        cwd=path,
    )
    if result.returncode != 0:
        raise SystemExit(f"ERROR: git commit failed for {path}\n{result.stderr.strip()}")


def _scaffold_arch_dirs(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / MODEL).mkdir(parents=True, exist_ok=True)
    (path / DOCS).mkdir(parents=True, exist_ok=True)
    (path / DIAGRAM_CATALOG / DIAGRAMS).mkdir(parents=True, exist_ok=True)
    (path / DIAGRAM_CATALOG / RENDERED).mkdir(parents=True, exist_ok=True)
    # Empty-repo init gets the full current default (base + assurance doc-types).
    ensure_arch_repo_defaults(path, document_schemas=DEFAULT_DOCUMENT_SCHEMAS)


def _commit_scaffold_changes(path: Path, *, commit_author_name: str, commit_author_email: str) -> None:
    """Commit the scaffolded structure, even when the repo already has unrelated commits."""
    _run_git(["add", "-A"], cwd=path)
    if not _git_output(["status", "--porcelain"], cwd=path).stdout.strip():
        return
    result = _git_output(
        ["-c", f"user.name={commit_author_name}", "-c", f"user.email={commit_author_email}",
         "commit", "-m", INITIAL_COMMIT_MESSAGE],
        cwd=path,
    )
    if result.returncode != 0:
        raise SystemExit(f"ERROR: git commit failed for {path}\n{result.stderr.strip()}")


def create_engagement_repo(
    path: Path,
    *,
    git_url: str | None = None,
    branch: str = "main",
    commit_author_name: str = "arch-switch-engagement",
    commit_author_email: str = "arch-switch-engagement@local.invalid",
) -> Path:
    if path.exists() and not path.is_dir():
        raise SystemExit(f"ERROR: engagement path exists but is not a directory: {path}")
    if path.exists() and any(path.iterdir()) and not (path / MODEL).is_dir():
        raise SystemExit(f"ERROR: engagement path exists but does not look like an architecture repository: {path}")

    _scaffold_arch_dirs(path)
    _ensure_git_repo(path, git_url=git_url, branch=branch)
    _commit_initial_scaffold(
        path,
        commit_author_name=commit_author_name,
        commit_author_email=commit_author_email,
    )
    return path.resolve()


def initialize_arch_repo_in_place(
    path: Path,
    *,
    commit_author_name: str = "arch-init",
    commit_author_email: str = "arch-init@local.invalid",
) -> Path:
    """Scaffold the arch-repo structure into an existing git checkout that lacks it.

    Unlike :func:`create_engagement_repo`, this is for a repo that is already a git
    checkout (cloned, possibly carrying unrelated commits such as a README). It adds the
    missing model/docs/diagram-catalog structure plus ``.arch-repo`` defaults and commits
    the additions. Idempotent: a no-op once ``model/`` exists.
    """
    if (path / MODEL).is_dir():
        return path.resolve()
    _scaffold_arch_dirs(path)
    _commit_scaffold_changes(
        path,
        commit_author_name=commit_author_name,
        commit_author_email=commit_author_email,
    )
    return path.resolve()
