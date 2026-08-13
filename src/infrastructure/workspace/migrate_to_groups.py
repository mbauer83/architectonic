"""Migration command: move the flat repository layout into the group-aware layout.

Performs one-commit-per-repo, idempotent migration:
  model/<domain>/<type>/…       → projects/<slug>/model/<domain>/<type>/…
  diagram-catalog/diagrams/<f>  → diagram-catalog/diagrams/uncategorized/<f>
  diagram-catalog/rendered/<f>  → diagram-catalog/rendered/uncategorized/<f>
  docs/<doc-type>/<f>           → docs/<doc-type>/uncategorized/<f>

Also seeds .arch-repo/groups.yaml and rewrites affected relative document links.

Run once per repo. Safe to re-run (no-op if already migrated).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.application.document_links import MARKDOWN_LINK_RE, is_external_or_anchor_href
from src.application.group_registry import _new_group_id, registry_to_yaml, write_groups_schema
from src.config.repo_paths import ARCH_REPO, DIAGRAM_CATALOG, DIAGRAMS, DOCS, MODEL, RENDERED
from src.domain.repository.groups import UNCATEGORIZED, GroupEntry, GroupRegistry


@dataclass
class MigrationResult:
    repo_root: Path
    already_migrated: bool
    moved_files: int
    rewritten_links: int
    groups_yaml_written: bool
    message: str


def _is_migrated(repo_root: Path) -> bool:
    """Return True if the repo already has the target group-aware layout."""
    return (repo_root / "projects").exists() or (repo_root / ARCH_REPO / "groups.yaml").exists()


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _git_mv(src: Path, dst: Path, cwd: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = _run_git(["mv", str(src.relative_to(cwd)), str(dst.relative_to(cwd))], cwd)
    if result.returncode != 0:
        raise RuntimeError(f"git mv failed: {result.stderr}")


def _slug_from_label(label: str) -> str:
    return label.lower().replace("_", "-").replace(" ", "-")


def _rewrite_links_in_doc(
    doc_path: Path,
    path_moves: dict[Path, Path],
    doc_new_path: Path,
) -> int:
    """Rewrite relative markdown links in doc_path after a batch of path moves.

    path_moves: {old_resolved → new_resolved} for every moved file.
    doc_new_path: the final location of this document after its own move.
    Returns the number of links rewritten.
    """
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError:
        return 0

    rewrites = 0
    doc_dir = doc_new_path.parent

    def _replace(m: re.Match[str]) -> str:
        nonlocal rewrites
        href = m.group(3)
        if is_external_or_anchor_href(href):
            return m.group(0)
        # Resolve relative to the *old* doc location (it hasn't moved yet when we call this)
        old_doc_dir = doc_path.parent
        try:
            resolved = (old_doc_dir / href).resolve()
        except OSError:
            return m.group(0)
        new_target = path_moves.get(resolved)
        if new_target is None:
            return m.group(0)
        try:
            new_rel = new_target.relative_to(doc_dir).as_posix()
        except ValueError:
            import posixpath

            new_rel = posixpath.relpath(str(new_target), str(doc_dir))
        rewrites += 1
        return f"{m.group(1)}{new_rel}{m.group(4)}"

    new_text = MARKDOWN_LINK_RE.sub(_replace, text)
    if new_text != text:
        doc_path.write_text(new_text, encoding="utf-8")
    return rewrites


def migrate_repo(repo_root: Path, *, dry_run: bool = False) -> MigrationResult:
    """Run the group-layout migration for a single repo.

    Returns a MigrationResult. Mutates nothing when dry_run=True.
    """
    repo_root = repo_root.resolve()

    if _is_migrated(repo_root):
        return MigrationResult(
            repo_root=repo_root,
            already_migrated=True,
            moved_files=0,
            rewritten_links=0,
            groups_yaml_written=False,
            message="Already migrated — no changes made.",
        )

    # Derive engagement label from repo root name heuristic
    from src.domain.ontology_representation.artifact_types import infer_mount  # noqa: PLC0415

    mount = infer_mount(repo_root)
    engagement_label = mount.engagement_label or "default"
    project_slug = _slug_from_label(engagement_label)

    # ── Build the list of moves ──────────────────────────────────────────────
    # path_moves: {old_resolved → new_resolved}
    path_moves: dict[Path, Path] = {}

    # 1. model/ → projects/<slug>/model/
    old_model = repo_root / MODEL
    new_model = repo_root / "projects" / project_slug / MODEL
    if old_model.exists():
        for p in sorted(old_model.rglob("*")):
            if p.is_file():
                rel = p.resolve().relative_to(old_model.resolve())
                path_moves[p.resolve()] = (new_model / rel).resolve()

    # 2. diagram-catalog/diagrams/<file> → diagram-catalog/diagrams/uncategorized/<file>
    old_diagrams = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    new_diagrams = repo_root / DIAGRAM_CATALOG / DIAGRAMS / UNCATEGORIZED
    if old_diagrams.exists():
        for p in sorted(old_diagrams.iterdir()):
            if p.is_file():
                path_moves[p.resolve()] = (new_diagrams / p.name).resolve()

    # 3. diagram-catalog/rendered/<file> → diagram-catalog/rendered/uncategorized/<file>
    old_rendered = repo_root / DIAGRAM_CATALOG / RENDERED
    new_rendered = repo_root / DIAGRAM_CATALOG / RENDERED / UNCATEGORIZED
    if old_rendered.exists():
        for p in sorted(old_rendered.iterdir()):
            if p.is_file():
                path_moves[p.resolve()] = (new_rendered / p.name).resolve()

    # 4. docs/<doc-type>/<file> → docs/<doc-type>/uncategorized/<file>
    old_docs = repo_root / DOCS
    if old_docs.exists():
        for doc_type_dir in sorted(old_docs.iterdir()):
            if doc_type_dir.is_dir():
                for p in sorted(doc_type_dir.iterdir()):
                    if p.is_file():
                        path_moves[p.resolve()] = (doc_type_dir / UNCATEGORIZED / p.name).resolve()

    if dry_run:
        return MigrationResult(
            repo_root=repo_root,
            already_migrated=False,
            moved_files=len(path_moves),
            rewritten_links=0,
            groups_yaml_written=True,
            message=f"Dry run: would move {len(path_moves)} files.",
        )

    # ── Rewrite document links BEFORE moving (while old paths are valid) ────
    total_rewrites = 0
    if old_docs.exists():
        for p in sorted(old_docs.rglob("*.md")):
            new_p = path_moves.get(p.resolve(), p.resolve())
            total_rewrites += _rewrite_links_in_doc(p, path_moves, new_p)

    # ── Execute moves via git mv ─────────────────────────────────────────────
    moved = 0
    errors: list[str] = []
    for old, new in path_moves.items():
        old_path = Path(old)
        new_path = Path(new)
        if not old_path.exists():
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _git_mv(old_path, new_path, repo_root)
            moved += 1
        except RuntimeError as exc:
            # Fall back to shutil.move if not in a git repo
            shutil.move(str(old_path), str(new_path))
            moved += 1
            errors.append(str(exc))

    # ── Seed groups.yaml ─────────────────────────────────────────────────────
    project_entry = GroupEntry(
        slug=project_slug,
        id=_new_group_id(),
        name=engagement_label.replace("-", " ").title(),
        default=True,
    )
    uncategorized_entry = GroupEntry(
        slug=UNCATEGORIZED,
        id=f"GRP@0.{UNCATEGORIZED}",
        name="Uncategorized",
    )
    registry = GroupRegistry(
        model_projects=(project_entry, uncategorized_entry),
        diagram_collections=(uncategorized_entry,),
        document_collections=(uncategorized_entry,),
    )
    arch_repo_dir = repo_root / ARCH_REPO
    arch_repo_dir.mkdir(parents=True, exist_ok=True)
    groups_path = arch_repo_dir / "groups.yaml"
    groups_path.write_text(registry_to_yaml(registry), encoding="utf-8")
    write_groups_schema(repo_root)

    _run_git(["add", str(groups_path.relative_to(repo_root))], repo_root)

    status_parts = [f"Migrated {moved} files"]
    if total_rewrites:
        status_parts.append(f"rewrote {total_rewrites} document links")
    if errors:
        status_parts.append(f"({len(errors)} git mv fallbacks)")

    return MigrationResult(
        repo_root=repo_root,
        already_migrated=False,
        moved_files=moved,
        rewritten_links=total_rewrites,
        groups_yaml_written=True,
        message="; ".join(status_parts) + ".",
    )


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Migrate arch-repo to the group-aware layout.")
    parser.add_argument("repo_root", nargs="?", help="Repository root (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without modifying files")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()
    result = migrate_repo(root, dry_run=args.dry_run)

    print(f"{'[dry-run] ' if args.dry_run else ''}{result.message}")
    if result.already_migrated:
        sys.exit(0)

    print(f"  moved files  : {result.moved_files}")
    print(f"  doc rewrites : {result.rewritten_links}")
    print(f"  groups.yaml  : {'written' if result.groups_yaml_written else 'skipped'}")


if __name__ == "__main__":
    main()
