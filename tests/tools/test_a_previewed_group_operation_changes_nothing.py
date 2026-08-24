"""`dry_run` means the same thing for every group action, and the result says what happened.

It did not. The flag was declared with a default of `True` and read by one branch of one action —
the cascade delete of a model project. `create`, `rename`, `archive`, `unarchive`, `update`, and the
deletion of a diagram- or document-collection all mutated the repository whatever it said. A caller
previewing a group creation got the group, and `{"action": "created", …}` is exactly what a faithful
preview would also have answered, so nothing in the result distinguished the two.

Stated over every action the dispatch offers rather than over the ones that were broken: the point is
that the flag cannot be honoured by five of six again.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.application.group_registry import load_group_registry
from src.infrastructure.write.artifact_write.group_ops import group_op

#: Every action `group_op` dispatches, with the arguments that make it a valid call, and what an
#: applied call is expected to change about the registry.
_ACTIONS = [
    ("create", {"target": "fresh", "name": "Fresh"}),
    ("rename", {"target": "existing", "new_slug": "renamed", "name": "Renamed"}),
    ("archive", {"target": "existing", "confirm": "existing"}),
    ("unarchive", {"target": "archived-one"}),
    ("update", {"target": "existing", "name": "Different"}),
    ("delete", {"target": "existing", "confirm": "existing"}),
]


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for command in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "test@test.com"],
        ["git", "config", "user.name", "Test"],
    ):
        subprocess.run(command, cwd=path, check=True, capture_output=True)
    (path / ".gitkeep").write_text("")
    subprocess.run(["git", "add", ".gitkeep"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _git_init(root)
    (root / "model").mkdir(parents=True, exist_ok=True)
    group_op(root, axis="diagram-collection", action="create", target="existing", name="Existing")
    group_op(root, axis="diagram-collection", action="create", target="archived-one", name="Archived")
    group_op(root, axis="diagram-collection", action="archive", target="archived-one")
    return root


def _registry_text(repo: Path) -> str:
    path = repo / ".arch-repo" / "groups.yaml"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.mark.parametrize(("action", "kwargs"), _ACTIONS, ids=[a for a, _ in _ACTIONS])
def test_a_previewed_action_leaves_the_registry_untouched(
    repo: Path, action: str, kwargs: dict[str, object]
) -> None:
    before = _registry_text(repo)

    result = group_op(repo, axis="diagram-collection", action=action, dry_run=True, **kwargs)

    assert _registry_text(repo) == before, f"{action} wrote groups.yaml during a preview"
    assert result["dry_run"] is True
    assert result["wrote"] is False


@pytest.mark.parametrize(("action", "kwargs"), _ACTIONS, ids=[a for a, _ in _ACTIONS])
def test_an_applied_action_says_it_wrote(
    repo: Path, action: str, kwargs: dict[str, object]
) -> None:
    result = group_op(repo, axis="diagram-collection", action=action, dry_run=False, **kwargs)

    assert result["dry_run"] is False
    assert result["wrote"] is True
    assert _registry_text(repo) != "", "an applied action persisted the registry"


def test_a_preview_still_refuses_what_an_applied_call_would_refuse(repo: Path) -> None:
    """A preview that skipped validation would be worse than none: it would report a success the
    real call cannot deliver."""
    from src.infrastructure.write.artifact_write.group_ops import GroupOpError

    with pytest.raises(GroupOpError, match="already exists"):
        group_op(repo, axis="diagram-collection", action="create", target="existing",
                 name="Existing", dry_run=True)


def test_a_previewed_delete_keeps_the_groups_files(repo: Path) -> None:
    """The most destructive action, and the one whose preview was ignored for two of three axes."""
    drawing = repo / "diagrams" / "existing" / "DGM@1780000001.aaaaaa.probe.md"
    drawing.parent.mkdir(parents=True, exist_ok=True)
    drawing.write_text("---\nartifact-id: DGM@1780000001.aaaaaa.probe\n---\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    result = group_op(repo, axis="diagram-collection", action="delete", target="existing",
                      confirm="existing", dry_run=True)

    assert drawing.exists(), "a previewed delete removed the group's files"
    assert result["wrote"] is False
    assert load_group_registry(repo).find("diagram-collection", "existing") is not None
