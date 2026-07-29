"""Summarise uncommitted git changes in an artifact repository.

Returns one record per artifact (entity/document/diagram) describing which
aspects changed: frontmatter, body, connections, or content.
Outgoing-connection file changes are merged into their source entity's record.

Used exclusively by the GUI save-dialog; not exposed via MCP.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

from src.config.repo_paths import DIAGRAM_CATALOG, DOCS, MODEL

_FM_RE = re.compile(r"^---\n(.*?)\n---\s*\n?", re.DOTALL)


def list_changes(repo_root: Path) -> list[dict]:
    """Return one dict per changed artifact, merging all related file changes."""
    repo = repo_root.resolve()

    # git status paths are relative to the git root, which may be an ancestor
    # of repo_root (e.g., a monorepo).  Compute the prefix to strip.
    rc, top_out = _run(repo, "rev-parse", "--show-toplevel")
    git_top = Path(top_out.strip()).resolve() if rc == 0 else repo
    try:
        prefix = repo.relative_to(git_top)  # e.g. "engagements/ENG-ARCH-REPO/architecture-repository"
    except ValueError:
        prefix = Path(".")

    entries: dict[str, dict] = {}
    for xy, git_rel in _git_porcelain(repo):
        # Convert git-root-relative path → repo-root-relative path
        abs_path = git_top / git_rel
        try:
            rel = str(abs_path.relative_to(repo))
        except ValueError:
            continue  # not under this repo_root
        kind = _classify(rel)
        if kind is None:
            continue
        # For git show, we need the git-root-relative path
        git_path = str(prefix / rel) if prefix != Path(".") else rel
        if kind == "connections":
            _handle_outgoing(repo, rel, git_path, xy, entries)
        else:
            _handle_artifact(repo, rel, git_path, xy, kind, entries)
    return list(entries.values())


# ─── Git helpers ──────────────────────────────────────────────────────────────


def _run(repo: Path, *args: str) -> tuple[int, str]:
    from src.infrastructure.git.git_env import get_ssh_env

    r = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        env=get_ssh_env(),
    )
    return r.returncode, r.stdout


def _git_porcelain(repo: Path) -> list[tuple[str, str]]:
    rc, out = _run(repo, "status", "--porcelain", "-u")
    if rc != 0:
        return []
    result = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        result.append((line[:2].strip(), line[3:]))
    return result


def _git_show(repo: Path, git_rel: str) -> str | None:
    """Retrieve HEAD content using the git-root-relative path."""
    rc, out = _run(repo, "show", f"HEAD:{git_rel}")
    return out if rc == 0 else None


# ─── Path classification ──────────────────────────────────────────────────────


def _classify(rel: str) -> str | None:
    parts = Path(rel).parts
    if not parts:
        return None
    top = parts[0]
    if top == MODEL:
        if rel.endswith(".outgoing.md"):
            return "connections"
        return "entity" if rel.endswith(".md") else None
    if top == DOCS:
        return "document" if rel.endswith(".md") else None
    if top == DIAGRAM_CATALOG:
        return "diagram"
    return None


# ─── Content helpers ──────────────────────────────────────────────────────────


def _split_fm(text: str) -> tuple[str, str]:
    m = _FM_RE.match(text)
    return (m.group(1), text[m.end() :].strip()) if m else ("", text.strip())


def _parse_fm(text: str) -> dict:
    fm_text, _ = _split_fm(text)
    if not fm_text:
        return {}
    try:
        return yaml.safe_load(fm_text) or {}
    except Exception:
        return {}


def _file_status(xy: str) -> str:
    if "D" in xy:
        return "deleted"
    if xy == "??" or xy.startswith("A"):
        return "added"
    return "modified"


def _diff_changes(old: str, new: str, kind: str) -> list[str]:
    if kind == "diagram":
        return ["content"] if old.strip() != new.strip() else []
    old_fm, old_body = _split_fm(old)
    new_fm, new_body = _split_fm(new)
    changes = []
    if old_fm.strip() != new_fm.strip():
        changes.append("frontmatter")
    if old_body.strip() != new_body.strip():
        changes.append("body")
    return changes or ["content"]


# ─── Per-file handlers ────────────────────────────────────────────────────────


def _handle_artifact(
    repo: Path,
    rel: str,
    git_path: str,
    xy: str,
    kind: str,
    entries: dict[str, dict],
) -> None:
    file_status = _file_status(xy)
    path = repo / rel

    curr = path.read_text("utf-8", errors="replace") if path.exists() else None
    head = _git_show(repo, git_path) if file_status != "added" else None
    fm = _parse_fm(curr or head or "")

    artifact_id = str(fm.get("artifact-id") or Path(rel).stem)
    name = str(fm.get("name") or fm.get("title") or artifact_id)
    artifact_type = fm.get("artifact-type") or fm.get("diagram-type") or fm.get("doc-type")

    if file_status in ("added", "deleted"):
        changes: list[str] = []
    else:
        changes = _diff_changes(head or "", curr or "", kind)

    if artifact_id in entries:
        combined = list(set(entries[artifact_id]["changes"] + changes))
        entries[artifact_id]["changes"] = combined
    else:
        entries[artifact_id] = {
            "artifact_id": artifact_id,
            "name": name,
            "record_type": kind,
            "artifact_type": str(artifact_type) if artifact_type else None,
            "file_status": file_status,
            "changes": changes,
        }


def _handle_outgoing(
    repo: Path,
    rel: str,
    git_path: str,
    xy: str,
    entries: dict[str, dict],
) -> None:
    path = repo / rel
    file_status = _file_status(xy)

    curr = path.read_text("utf-8", errors="replace") if path.exists() else None
    head = _git_show(repo, git_path) if file_status != "added" else None
    fm = _parse_fm(curr or head or "")

    source_id = str(fm.get("source-entity") or "")
    if not source_id:
        return

    if source_id in entries:
        if "connections" not in entries[source_id]["changes"]:
            entries[source_id]["changes"].append("connections")
    else:
        entries[source_id] = {
            "artifact_id": source_id,
            "name": source_id,
            "record_type": "entity",
            "artifact_type": None,
            "file_status": "modified",
            "changes": ["connections"],
        }
