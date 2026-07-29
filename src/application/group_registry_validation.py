"""Startup validation and auto-repair for group registries.

Single pass:
1. Load registry — raises GroupRegistryError on YAML syntax errors, schema failures,
   or invalid meta_ontology values.
2. Filesystem reconciliation — auto-registers group directories that contain artifacts
   but have no registry entry (writable repos) or logs warnings (read-only repos).

Write errors are surfaced as GroupRegistryError; git-add failures are non-fatal
but appended to the returned message list.
"""

from __future__ import annotations

import random
import string
import subprocess
from pathlib import Path

import yaml

from src.application.group_registry import load_group_registry, registry_to_yaml
from src.domain.clock import epoch_seconds
from src.domain.repository.groups import UNCATEGORIZED, GroupAxis, GroupEntry, GroupRegistry
from src.domain.repository.repo_layout import ARCH_REPO, DIAGRAM_CATALOG, DIAGRAMS, DOCS

_GROUPS_FILE = "groups.yaml"


class GroupRegistryError(ValueError):
    """Raised when the group registry has issues that cannot be auto-repaired."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("\n".join(errors))


def validate_and_repair_group_registry(
    repo_root: Path,
    *,
    valid_meta_ontologies: frozenset[str],
    read_only: bool = False,
) -> list[str]:
    """Validate and optionally repair the group registry for a repository root.

    Loads the registry once (raising GroupRegistryError on YAML/schema errors or
    invalid meta_ontology values), then reconciles the filesystem: group directories
    that contain artifacts but have no registry entry are auto-registered (writable
    repos) or reported as warnings (read-only repos).

    Returns a list of informational messages (repairs performed / warnings).
    Raises GroupRegistryError for issues that cannot be auto-repaired.
    """
    messages: list[str] = []

    # Load and validate — single file read; catches YAML syntax, schema, and I/O errors.
    try:
        registry = load_group_registry(repo_root)
    except yaml.YAMLError as exc:
        raise GroupRegistryError([
            f".arch-repo/groups.yaml has invalid YAML syntax: {exc}",
            f"File: {repo_root / ARCH_REPO / _GROUPS_FILE}",
        ])
    except Exception as exc:
        raise GroupRegistryError([f"Failed to load .arch-repo/groups.yaml: {exc}"])

    bad_ontologies = [
        f"Model-project {e.slug!r}: unknown meta_ontology {e.meta_ontology!r} — "
        f"valid values: {_format_valid_meta_ontologies(valid_meta_ontologies)}"
        for e in registry.model_projects
        if e.meta_ontology and e.meta_ontology not in valid_meta_ontologies
    ]
    if bad_ontologies:
        raise GroupRegistryError(bad_ontologies)

    # Filesystem reconciliation — scan each axis for orphaned directories.
    changed = False

    def _reconcile(axis: GroupAxis, slug_dir: Path, ext: str) -> None:
        nonlocal changed, registry
        slug = slug_dir.name
        if slug == UNCATEGORIZED or registry.find(axis, slug) is not None:
            return
        if not any(slug_dir.rglob(f"*.{ext}")):
            return
        if read_only:
            messages.append(f"Warning: {axis} directory {slug!r} has {ext} files but no registry entry")
            return
        registry = _register_orphan(registry, axis, slug)
        changed = True
        messages.append(f"Auto-registered orphaned {axis}: {slug!r}")

    projects_dir = repo_root / "projects"
    if projects_dir.exists():
        for d in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
            _reconcile("model-project", d, "yaml")

    diag_root = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    if diag_root.exists():
        for d in sorted(p for p in diag_root.iterdir() if p.is_dir()):
            _reconcile("diagram-collection", d, "puml")

    docs_dir = repo_root / DOCS
    seen: set[str] = set()
    if docs_dir.exists():
        for doc_type_dir in sorted(p for p in docs_dir.iterdir() if p.is_dir()):
            for d in sorted(p for p in doc_type_dir.iterdir() if p.is_dir()):
                if d.name not in seen:
                    _reconcile("document-collection", d, "md")
                    seen.add(d.name)

    if changed:
        _persist_registry(repo_root, registry, messages)

    return messages


def _format_valid_meta_ontologies(values: frozenset[str]) -> str:
    shown = sorted(v for v in values if v)
    return ", ".join(repr(v) for v in shown) if shown else "<none>"


# ── Internal helpers ──────────────────────────────────────────────────────────


def _persist_registry(repo_root: Path, registry: GroupRegistry, messages: list[str]) -> None:
    """Write the repaired registry to disk and stage it; raises GroupRegistryError on I/O failure."""
    arch_dir = repo_root / ARCH_REPO
    out_path = arch_dir / _GROUPS_FILE
    try:
        arch_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(registry_to_yaml(registry), encoding="utf-8")
    except OSError as exc:
        raise GroupRegistryError([f"Failed to write repaired {_GROUPS_FILE}: {exc}"])
    result = subprocess.run(
        ["git", "add", str(out_path.relative_to(repo_root))],
        cwd=repo_root, capture_output=True, check=False,
    )
    if result.returncode != 0:
        messages.append(
            f"Warning: could not stage {_GROUPS_FILE} — "
            f"git add exited {result.returncode}: {result.stderr.decode().strip()}"
        )


def _new_id() -> str:
    epoch, rand = epoch_seconds(), "".join(random.choices(string.ascii_letters + string.digits, k=6))
    return f"GRP@{epoch}.{rand}"


def _register_orphan(registry: GroupRegistry, axis: GroupAxis, slug: str) -> GroupRegistry:
    from dataclasses import replace
    entry = GroupEntry(slug=slug, id=_new_id(), name=slug.replace("-", " ").title())
    entries = list(registry._by_axis(axis)) + [entry]
    if axis == "model-project":
        return replace(registry, model_projects=tuple(entries))
    if axis == "diagram-collection":
        return replace(registry, diagram_collections=tuple(entries))
    return replace(registry, document_collections=tuple(entries))
