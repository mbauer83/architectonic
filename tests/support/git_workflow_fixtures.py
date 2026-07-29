"""Real-git fixture builder for REST workflow tests (save / submit / withdraw /
promote). Builds an engagement repo and an enterprise repo with a local bare
origin, both on ``main`` with one valid committed artifact each.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ENG_ENTITY_ID = "REQ@1000000601.WfEng.workflow-engagement-requirement"
ENT_ENTITY_ID = "REQ@1000000602.WfEnt.workflow-enterprise-requirement"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def valid_entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
    return (
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: requirement\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        "<!-- §content -->\n\n"
        f"## {name}\n\n"
        "Workflow fixture.\n\n"
        "## Properties\n\n"
        "| Attribute | Value |\n"
        "|---|---|\n"
        "| (none) | (none) |\n\n"
        "<!-- §display -->\n\n"
        "### archimate\n\n"
        "```yaml\n"
        f"label: {name}\n"
        f"alias: REQ_{slug}\n"
        "```\n"
    )


def write_entity(root: Path, artifact_id: str, name: str) -> Path:
    path = root / "model" / "motivation" / "requirement" / f"{artifact_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(valid_entity_md(artifact_id, name), encoding="utf-8")
    return path


def init_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "workflow@example.invalid")
    git(root, "config", "user.name", "Workflow Fixture")
    git(root, "add", "-A")
    git(root, "commit", "-m", "seed", "--allow-empty")


def add_bare_origin(root: Path, bare_dir: Path) -> Path:
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare_dir)], check=True, capture_output=True)
    git(root, "remote", "add", "origin", str(bare_dir))
    git(root, "push", "-u", "origin", "main")
    return bare_dir


def build_workflow_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Engagement + enterprise real git repos; enterprise has a bare origin."""
    engagement = tmp_path / "engagements" / "ENG-WFL" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    write_entity(engagement, ENG_ENTITY_ID, "Workflow Engagement Requirement")
    write_entity(enterprise, ENT_ENTITY_ID, "Workflow Enterprise Requirement")
    init_git_repo(engagement)
    init_git_repo(enterprise)
    add_bare_origin(enterprise, tmp_path / "enterprise-origin.git")
    return engagement, enterprise
