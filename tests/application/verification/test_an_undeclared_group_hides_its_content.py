"""W046: content filed under a group no axis declares is content navigation cannot reach.

`artifact_create_entity(group="payments")` writes `projects/payments/model/…` whether or not
`payments` is a declared model project, because the group is a property of the path and the path is
valid either way. Verification passed on every such file, so entities could accumulate for weeks in a
directory the GUI's model navigation had nothing to list them under — reachable by search and by id,
absent from everywhere a person browses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier

_ENTITY = """---
artifact-id: {aid}
artifact-type: requirement
name: {name}
version: 0.1.0
status: draft
---

## Content
A requirement.
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_in(repo: Path, project: str, aid: str, name: str) -> None:
    _write(
        repo / "projects" / project / "model" / "motivation" / "requirement" / f"{aid}.md",
        _ENTITY.format(aid=aid, name=name),
    )


def _declare(repo: Path, slug: str, *, name: str) -> None:
    from src.infrastructure.write.artifact_write.group_ops import group_op

    group_op(repo, axis="model-project", action="create", target=slug, name=name)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True, exist_ok=True)
    return root


def _w046(repo: Path) -> list[str]:
    """Every W046 message from a full pass, driven the way the product drives it."""
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
    from src.infrastructure.artifact_index import shared_artifact_index

    index = shared_artifact_index(repo)
    index.refresh()
    verifier = ArtifactVerifier(
        ArtifactRegistry(index),
        check_puml_syntax=False,
        catalogs=build_runtime_catalogs(build_module_registry()),
    )
    return [
        issue.message
        for result in verifier.verify_all(repo)
        for issue in result.issues
        if issue.code == "W046"
    ]


def test_an_undeclared_project_is_reported_with_what_it_holds(repo: Path) -> None:
    _entity_in(repo, "payments", "REQ@1780000001.aaaaaa.one", "One")
    _entity_in(repo, "payments", "REQ@1780000002.aaaaaa.two", "Two")

    messages = _w046(repo)

    assert len(messages) == 1, messages
    assert "payments" in messages[0]
    assert "2 model files" in messages[0]
    assert "model-project" in messages[0]


def test_a_declared_project_is_not_reported(repo: Path) -> None:
    _declare(repo, "payments", name="Payments")
    _entity_in(repo, "payments", "REQ@1780000001.aaaaaa.one", "One")

    assert _w046(repo) == []


def test_the_legacy_model_root_is_not_a_group_at_all(repo: Path) -> None:
    """Content directly under `model/` is `uncategorized`, which every registry declares. Reporting
    it would fire on every repository that has not adopted projects."""
    _write(
        repo / "model" / "motivation" / "requirement" / "REQ@1780000003.aaaaaa.legacy.md",
        _ENTITY.format(aid="REQ@1780000003.aaaaaa.legacy", name="Legacy"),
    )

    assert _w046(repo) == []


def test_each_undeclared_group_is_reported_once_however_much_it_holds(repo: Path) -> None:
    """One finding per group, not per file: the thing to fix is the missing registry row."""
    for index in range(4):
        _entity_in(repo, "alpha", f"REQ@178000001{index}.aaaaaa.a{index}", f"A{index}")
    _entity_in(repo, "beta", "REQ@1780000020.aaaaaa.b", "B")

    messages = sorted(_w046(repo))

    assert len(messages) == 2, messages
    assert "'alpha' holds 4 model files" in messages[0]
    assert "'beta' holds 1 model file" in messages[1], "one file is not '1 files'"


def test_declaring_the_group_clears_the_finding(repo: Path) -> None:
    """The regression as a person meets it: the fix is one registry row, and verification says so."""
    _entity_in(repo, "payments", "REQ@1780000001.aaaaaa.one", "One")
    assert _w046(repo) != []

    _declare(repo, "payments", name="Payments")

    assert _w046(repo) == []
