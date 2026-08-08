"""The MCP tools answer for the workspace this backend serves, not the one its code sits in.

Found by running two backends on one machine. The second was given its own `--repo-root`,
`--enterprise-root` and `arch-workspace.yaml`; `/api/backend-identity` truthfully reported those
roots; and its MCP tools read the *first* workspace's repository — 880 files from a directory that
was empty. Nothing failed. The wrong repository simply answered.

The cause was that the MCP layer resolved its default roots from `Path(__file__).parents[4]`, which
is where the code lives. That coincides with the workspace in a developer's checkout, and in the
container where `arch-workspace.yaml` is mounted beside the code at `/app` — which is why it stayed
invisible. It stops coinciding the moment one installed copy serves a different directory.

Twelve MCP modules share this resolution, `write/entity.py`, `write/connection.py` and
`delete_tools.py` among them, so this was not confined to reads: an authored entity or a delete could
land in a neighbouring workspace's model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp.artifact_mcp import context
from src.infrastructure.rest.routers import state as gui_state


@pytest.fixture()
def two_workspaces(tmp_path: Path):
    """A served workspace, and a different one that the code might be sitting in."""
    served_engagement = tmp_path / "served" / "engagements" / "ENG-SERVED" / "architecture-repository"
    served_enterprise = tmp_path / "served" / "enterprise-repository"
    other = tmp_path / "elsewhere"
    for path in (served_engagement, served_enterprise, other):
        path.mkdir(parents=True, exist_ok=True)
    return served_engagement, served_enterprise, other


def test_the_default_roots_are_the_ones_the_backend_serves(
    two_workspaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    served_engagement, served_enterprise, other = two_workspaces
    monkeypatch.setattr(context, "workspace_root", lambda: other)
    monkeypatch.delenv("ARCH_MCP_MODEL_REPO_ROOT", raising=False)
    monkeypatch.delenv("ARCH_REPO_ROOT", raising=False)
    monkeypatch.delenv("ARCH_ENTERPRISE_ROOT", raising=False)
    monkeypatch.setattr(
        gui_state, "configured_roots", lambda: [served_engagement, served_enterprise]
    )

    assert context.default_engagement_repo_root() == served_engagement
    assert context.default_enterprise_repo_root() == served_enterprise


def test_a_repo_preset_also_follows_the_served_workspace(
    two_workspaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`repo_preset` resolves through the same roots, so it carried the same defect."""
    served_engagement, served_enterprise, other = two_workspaces
    monkeypatch.setattr(context, "workspace_root", lambda: other)
    monkeypatch.setattr(
        gui_state, "configured_roots", lambda: [served_engagement, served_enterprise]
    )

    assert context.repo_root_from_preset("engagement") == served_engagement
    assert context.repo_root_from_preset("enterprise") == served_enterprise


def test_outside_a_backend_the_code_relative_workspace_is_still_the_fallback(
    two_workspaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process with no served roots — no REST state installed — keeps the old behaviour."""
    _served_engagement, _served_enterprise, other = two_workspaces
    fallback_engagement = other / "engagements" / "ENG-FALLBACK" / "architecture-repository"
    fallback_enterprise = other / "enterprise-repository"
    fallback_engagement.mkdir(parents=True, exist_ok=True)
    fallback_enterprise.mkdir(parents=True, exist_ok=True)
    (other / "arch-workspace.yaml").write_text(
        f"engagement:\n  local: {fallback_engagement}\n\nenterprise:\n  local: {fallback_enterprise}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(context, "workspace_root", lambda: other)
    monkeypatch.setattr(gui_state, "configured_roots", list)
    monkeypatch.delenv("ARCH_MCP_MODEL_REPO_ROOT", raising=False)
    monkeypatch.delenv("ARCH_REPO_ROOT", raising=False)

    assert context.default_engagement_repo_root() == fallback_engagement


def test_an_explicit_root_still_wins_over_both(two_workspaces, monkeypatch: pytest.MonkeyPatch) -> None:
    served_engagement, served_enterprise, other = two_workspaces
    monkeypatch.setattr(context, "workspace_root", lambda: other)
    monkeypatch.setattr(
        gui_state, "configured_roots", lambda: [served_engagement, served_enterprise]
    )
    explicit = other / "explicitly-asked-for"
    explicit.mkdir(parents=True, exist_ok=True)

    resolved = context.resolve_repo_roots(
        repo_scope="engagement", repo_root=str(explicit), repo_preset=None, enterprise_root=None
    )

    assert resolved == [explicit]
