"""Summarise the uncommitted content of a repository: everything a save would commit.

One record per artifact (entity, document, diagram, icon, scratchpad) describing which aspects
changed — frontmatter, body, connections, or content — with an outgoing-connection file merged into
its source entity's record. Content that is no artifact, such as the repository's configuration,
is listed as the file it is.

**Every changed content file ends up in a row**, because the list is what the author confirms: it
left scratchpads out on purpose and everything outside the artifact layout by default, so the
dialog could read "no tracked changes" over a save that then committed some. Which files are
content is not decided here — the status is asked the same question the save and the pull ask.

Used exclusively by the GUI save-dialog; not exposed via MCP.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.config.repo_paths import DIAGRAM_CATALOG
from src.domain.repository.artifact_location import artifact_kind_at
from src.domain.repository.frontmatter import Frontmatter, read_frontmatter
from src.domain.repository.repo_layout import SCRATCHPAD_SUFFIX
from src.domain.yaml_documents import parse_yaml
from src.infrastructure.git.git_repository_state import UNCOMMITTED_CONTENT_QUERY


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
        # For git show, we need the git-root-relative path
        git_path = str(prefix / rel) if prefix != Path(".") else rel
        _HANDLERS.get(kind, _handle_artifact)(repo, rel, git_path, xy, kind, entries)
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
    rc, out = _run(repo, *UNCOMMITTED_CONTENT_QUERY)
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


def _classify(rel: str) -> str:
    """What a changed content file is saved as: the artifact it is part of, or the file it is.

    Sources are classified by the layout's one reading. What else changes under the diagram catalog
    (rendered pictures, generated includes) is derived output, saved with the diagrams it belongs to.
    Anything the layout gives no kind — configuration, a stray note — is still committed by a save,
    so it is listed as a `file` rather than left out: it is no artifact, and it is not nothing.
    """
    kind = artifact_kind_at(rel)
    if kind is None:
        return "diagram" if Path(rel).parts[:1] == (DIAGRAM_CATALOG,) else "file"
    # An entity's outgoing file is merged into its entity's row, under a heading of its own.
    return "connections" if kind == "connection" else kind


# ─── Content helpers ──────────────────────────────────────────────────────────


def _split_fm(text: str) -> tuple[str, str]:
    reading = read_frontmatter(text)
    return (reading.text, reading.body.strip()) if isinstance(reading, Frontmatter) else ("", text.strip())


def _parse_fm(text: str) -> dict:
    fm_text, _ = _split_fm(text)
    if not fm_text:
        return {}
    try:
        return parse_yaml(fm_text) or {}
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
    _kind: str,
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


def _handle_scratchpad(
    repo: Path,
    rel: str,
    git_path: str,
    xy: str,
    kind: str,
    entries: dict[str, dict],
) -> None:
    """A scratchpad is one YAML document with no frontmatter, so it is read as one.

    Its id is its file name — the layout's own statement, which also holds for a pad that was
    deleted and one whose text does not parse.
    """
    file_status = _file_status(xy)
    path = repo / rel
    text = path.read_text("utf-8", errors="replace") if path.exists() else _git_show(repo, git_path)
    artifact_id = Path(rel).name.removesuffix(SCRATCHPAD_SUFFIX)
    entries[artifact_id] = {
        "artifact_id": artifact_id,
        "name": str(_yaml_mapping(text or "").get("name") or artifact_id),
        "record_type": kind,
        "artifact_type": None,
        "file_status": file_status,
        "changes": ["content"] if file_status == "modified" else [],
    }


def _handle_file(
    _repo: Path,
    rel: str,
    _git_path: str,
    xy: str,
    kind: str,
    entries: dict[str, dict],
) -> None:
    """Content the layout gives no kind: identified by where it is, since that is all it has."""
    file_status = _file_status(xy)
    entries[rel] = {
        "artifact_id": rel,
        "name": Path(rel).name,
        "record_type": kind,
        "artifact_type": None,
        "file_status": file_status,
        "changes": ["content"] if file_status == "modified" else [],
    }


def _yaml_mapping(text: str) -> dict:
    try:
        loaded = parse_yaml(text)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


_HANDLERS = {"connections": _handle_outgoing, "scratchpad": _handle_scratchpad, "file": _handle_file}
