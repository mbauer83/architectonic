"""Pure file-reading helpers for cascade_delete.py."""

from __future__ import annotations

import re
from pathlib import Path

from src.domain.repository.frontmatter import Frontmatter, read_frontmatter
from src.domain.yaml_documents import parse_yaml
from src.infrastructure.mutation_adapters import run_git

_ID_RE = re.compile(r"^artifact-id:\s*(.+?)\s*$", re.MULTILINE)
_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_SRC_RE = re.compile(r"^source-entity:\s*(.+?)\s*$", re.MULTILINE)
_CONN_HDR_RE = re.compile(r"^### .+ → (.+)$", re.MULTILINE)


def read_frontmatter_id_name(path: Path) -> tuple[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    reading = read_frontmatter(text)
    if not isinstance(reading, Frontmatter):
        return None
    fm_text = reading.text
    id_m = _ID_RE.search(fm_text)
    name_m = _NAME_RE.search(fm_text)
    return (id_m.group(1), name_m.group(1) if name_m else path.stem) if id_m else None


def read_source_entity_id(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _SRC_RE.search(text)
    return m.group(1) if m else None


def read_connection_targets(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return _CONN_HDR_RE.findall(text)


def read_diagram_frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    reading = read_frontmatter(text)
    if not isinstance(reading, Frontmatter):
        return None
    try:
        return parse_yaml(reading.text) or {}
    except Exception:  # noqa: BLE001
        return None


def conn_touches(conn_id: str, entity_ids: set[str]) -> bool:
    return any(eid in conn_id for eid in entity_ids)


def conn_row_touches(conn_row: object, entity_ids: set[str]) -> bool:
    if not isinstance(conn_row, dict):
        return False
    return str(conn_row.get("source", "")) in entity_ids or str(conn_row.get("target", "")) in entity_ids


def is_puml_customised(diagram_path: Path, fm: dict) -> bool:
    """True if the PUML body differs from a fresh render of its diagram-entities."""
    from src.application.repo_path_helpers import repo_root_for_diagram_path  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.diagram_render import (  # noqa: PLC0415
        _render_diagram_entities_puml,
    )
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

    repo_root = repo_root_for_diagram_path(diagram_path)
    if repo_root is None:
        return True
    de = fm.get("diagram-entities")
    if not isinstance(de, dict):
        return True
    dc = fm.get("connections")
    try:
        expected = _render_diagram_entities_puml(
            str(fm.get("diagram-type", "archimate")),
            str(fm.get("name", "")),
            de,
            dc if isinstance(dc, list) else None,
            repo_root,
        )
        parsed = parse_diagram_file(diagram_path)
        return parsed.puml_body.strip() != expected.strip()
    except Exception:  # noqa: BLE001
        return True


def find_broken_links(doc_path: Path, owned_paths: set[Path], repo_root: Path) -> list[str]:  # noqa: ARG001
    """The hrefs in *doc_path* that point at something this delete is about to remove.

    A filter over `references_from`, which is the one reading of what a document's prose refers
    to. It used to be a second one, matching `](….md)` with its own regex — and that cannot match
    `](….md#properties)`, so a document linking into a *section* of an entity was invisible to the
    check whose whole job is to find what a deletion would break.
    """
    from src.application.document_links import references_from  # noqa: PLC0415

    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [
        reference.href
        for reference in references_from(text, directory=doc_path.parent)
        if reference.target in owned_paths
    ]


def remove_from_groups_yaml(repo_root: Path, project_slug: str) -> None:
    from dataclasses import replace  # noqa: PLC0415

    from src.application.group_registry import load_group_registry, registry_to_yaml  # noqa: PLC0415
    from src.config.repo_paths import ARCH_REPO  # noqa: PLC0415

    registry = load_group_registry(repo_root)
    entries = [e for e in registry.model_projects if e.slug != project_slug]
    if len(entries) == len(registry.model_projects):
        return
    updated = replace(registry, model_projects=tuple(entries))
    arch_dir = repo_root / ARCH_REPO
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / "groups.yaml").write_text(registry_to_yaml(updated), encoding="utf-8")


def rollback_cascade(backups: list[tuple[Path, bytes | None]], repo_root: Path) -> None:
    for path, original in reversed(backups):
        try:
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        except OSError:
            pass
    run_git(repo_root, ["reset", "HEAD"])
