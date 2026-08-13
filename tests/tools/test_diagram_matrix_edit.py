"""Tests for the matrix-diagram branch of artifact_edit_diagram/edit_diagram.

Regression coverage for the gap found during WU-C3 (grouping taxonomy): matrix
diagrams are markdown tables under diagram-catalog/diagrams/*.md, but
edit_diagram unconditionally ran the PUML pipeline (check_puml_structure
requires @startuml/@enduml) — so a matrix diagram had no working edit path at
all, including no way to re-home it into a group. diagram_edit.py now detects
diagram-type: matrix and delegates to matrix.edit_matrix_metadata (via
_diagram_matrix_edit.edit_matrix_diagram), which verifies with
verify_matrix_diagram_file instead and preserves the table body verbatim.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


def _make_matrix_diagram(repo: Path, artifact_id: str, name: str = "Matrix") -> Path:
    result = mcp.artifact_create_matrix(
        name=name,
        matrix_markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
        artifact_id=artifact_id,
        dry_run=False,
        repo_root=str(repo),
    )
    assert result["wrote"], result
    return repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.md"


def test_edit_diagram_group_relocates_matrix_diagram(repo: Path) -> None:
    artifact_id = "MAT@1778000010.tmtx.matrix-move"
    old_path = _make_matrix_diagram(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, group="landing-zone", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    new_path = repo / "diagram-catalog" / "diagrams" / "landing-zone" / f"{artifact_id}.md"
    assert new_path.exists()
    assert not old_path.exists()
    assert "| 1 | 2 |" in new_path.read_text(encoding="utf-8")


def test_edit_diagram_matrix_updates_metadata_preserves_table(repo: Path) -> None:
    artifact_id = "MAT@1778000011.tmtx.matrix-meta"
    path = _make_matrix_diagram(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, name="Renamed Matrix", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    fm = _read_fm(path)
    assert fm["name"] == "Renamed Matrix"
    assert "| 1 | 2 |" in path.read_text(encoding="utf-8")


def test_edit_diagram_matrix_dry_run_previews_without_moving(repo: Path) -> None:
    artifact_id = "MAT@1778000012.tmtx.matrix-preview"
    old_path = _make_matrix_diagram(repo, artifact_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=artifact_id, group="landing-zone", dry_run=True, repo_root=str(repo),
    )

    assert not result["wrote"]
    assert old_path.exists()
    new_path = repo / "diagram-catalog" / "diagrams" / "landing-zone" / f"{artifact_id}.md"
    assert not new_path.exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"puml": "@startuml\n@enduml\n"},
        {"diagram_entities": {"entity-ids": ["X@1.a.b"]}},
        {"bindings": [{"correspondence_kind": "represents"}]},
        {"edge_labels": {"a:b": "label"}},
        {"viewpoint": {"slug": "some-viewpoint"}},
    ],
)
def test_edit_diagram_matrix_rejects_puml_only_params(repo: Path, kwargs: dict) -> None:
    artifact_id = "MAT@1778000013.tmtx.matrix-reject"
    _make_matrix_diagram(repo, artifact_id)

    with pytest.raises(ValueError, match="do not support"):
        mcp.artifact_edit_diagram(
            artifact_id=artifact_id, dry_run=False, repo_root=str(repo), **kwargs,
        )


def test_edit_diagram_matrix_not_found_still_reports_clear_error(repo: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        mcp.artifact_edit_diagram(
            artifact_id="MAT@1778000099.tmtx.missing", name="x", dry_run=False, repo_root=str(repo),
        )


class TestAnUpsertKeepsWhatItIsNotToldAbout:
    """`artifact_create_matrix` upserts an existing matrix, and used to write only what the caller
    restated — dropping the axis declarations and the connection-type configuration, which are
    frontmatter an author declares and the MCP tool does not even expose. An agent handing back an
    edited body, to repair a link say, silently erased which entities the matrix relates."""

    def test_the_axes_and_conn_type_configs_survive_a_body_only_upsert(self, repo: Path) -> None:
        artifact_id = "MAT@1778000020.tmtx.matrix-upsert"
        first = mcp.artifact_create_matrix(
            name="Matrix", matrix_markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
            artifact_id=artifact_id, dry_run=False, repo_root=str(repo),
        )
        assert first["wrote"], first
        path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.md"
        # Declared directly, because the MCP tool has no parameter for them — which is the point.
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "artifact-type: diagram",
            "artifact-type: diagram\nfrom-entity-ids:\n- REQ@1.a.one\nto-entity-ids:\n- APP@1.b.two",
            1,
        )
        path.write_text(text, encoding="utf-8")

        mcp.artifact_create_matrix(
            name="Matrix", matrix_markdown="| A | B |\n|---|---|\n| 1 | 3 |\n",
            artifact_id=artifact_id, dry_run=False, repo_root=str(repo),
        )

        fm = _read_fm(path)
        assert fm.get("from-entity-ids") == ["REQ@1.a.one"]
        assert fm.get("to-entity-ids") == ["APP@1.b.two"]
        assert "| 1 | 3 |" in path.read_text(encoding="utf-8")

    def test_a_caller_that_states_an_axis_replaces_it(self, repo: Path) -> None:
        """Preserving the unstated must not make a stated one unsettable."""
        from src.infrastructure.mcp.artifact_mcp.context import registry_cached, roots_key, verifier_for
        from src.infrastructure.write.artifact_write import matrix as matrix_ops

        artifact_id = "MAT@1778000021.tmtx.matrix-restate"
        mcp.artifact_create_matrix(
            name="Matrix", matrix_markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
            artifact_id=artifact_id, dry_run=False, repo_root=str(repo),
        )
        path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.md"
        roots = (repo.resolve(),)
        key = roots_key(roots)

        matrix_ops.create_matrix(
            repo_root=repo.resolve(),
            registry=registry_cached(key),
            verifier=verifier_for(key, include_registry=True),
            clear_repo_caches=lambda _root: None,
            name="Matrix",
            matrix_markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
            artifact_id=artifact_id,
            from_entity_ids=["REQ@9.z.stated"],
            dry_run=False,
        )

        assert _read_fm(path).get("from-entity-ids") == ["REQ@9.z.stated"]
