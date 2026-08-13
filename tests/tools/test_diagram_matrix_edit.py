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


def _make_entity(repo: Path, artifact_id: str, name: str, artifact_type: str = "requirement") -> str:
    """A real entity in the fixture, so a matrix axis naming it resolves.

    Written directly rather than through a write tool: these tests are about the matrix, and the
    entity is scenery. Every axis test needs one because the axis is now resolved against the
    registry, which is the whole point of the rule.
    """
    domain = "motivation"
    path = repo / "model" / domain / artifact_type / f"{artifact_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nartifact-id: {artifact_id}\nartifact-type: {artifact_type}\nname: {name}\n"
        f"version: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n---\n\n"
        f"<!-- §content -->\n\n## {name}\n\nScenery.\n",
        encoding="utf-8",
    )
    return artifact_id


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
        row = _make_entity(repo, "REQ@1778000020.aaaa.a-row", "A Row")
        col = _make_entity(repo, "APP@1778000020.bbbb.a-column", "A Column", "application-component")
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
            f"artifact-type: diagram\nfrom-entity-ids:\n- {row}\nto-entity-ids:\n- {col}",
            1,
        )
        path.write_text(text, encoding="utf-8")

        mcp.artifact_create_matrix(
            name="Matrix", matrix_markdown="| A | B |\n|---|---|\n| 1 | 3 |\n",
            artifact_id=artifact_id, dry_run=False, repo_root=str(repo),
        )

        fm = _read_fm(path)
        assert fm.get("from-entity-ids") == [row]
        assert fm.get("to-entity-ids") == [col]
        assert "| 1 | 3 |" in path.read_text(encoding="utf-8")

    def test_a_caller_that_states_an_axis_replaces_it(self, repo: Path) -> None:
        """Preserving the unstated must not make a stated one unsettable."""
        from src.infrastructure.mcp.artifact_mcp.context import registry_cached, roots_key, verifier_for
        from src.infrastructure.write.artifact_write import matrix as matrix_ops

        artifact_id = "MAT@1778000021.tmtx.matrix-restate"
        stated = _make_entity(repo, "REQ@1778000021.cccc.stated", "Stated")
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
            from_entity_ids=[stated],
            dry_run=False,
        )

        assert _read_fm(path).get("from-entity-ids") == [stated]


class TestAnAxisNamesEntitiesThatExist:
    """A matrix declares its columns as `to-entity-ids` and its rows as `from-entity-ids`, and
    those lists were never resolved against the registry — only `entity-ids-used` was. Two outcome
    ids that had never been created sat in a `to-entity-ids` axis from the initial commit, drawing
    two columns of a traceability matrix and four ticks against requirements. Nothing asked whether
    they resolved; they surfaced only when a link check was pointed at diagram prose."""

    def test_a_write_whose_axis_names_a_missing_entity_is_refused(self, repo: Path) -> None:
        """End to end: the write path verifies before it commits, so an invented column id never
        reaches a file. This is what would have stopped the two hallucinated outcomes."""
        result = mcp.artifact_create_matrix(
            name="Matrix", matrix_markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
            artifact_id="MAT@1778000030.tmtx.matrix-axis",
            to_entity_ids=["OUT@9.zzz.never-created"],
            dry_run=False, repo_root=str(repo),
        )

        assert not result.get("wrote"), result
        assert "OUT@9.zzz.never-created" in str(result)

    def test_the_axis_is_resolved_the_way_entity_ids_used_is(self, repo: Path) -> None:
        """The rule itself, over a file that already holds the bad id — which is how the real one
        arrived: authored once, before anything resolved the axis."""
        from src.infrastructure.mcp.artifact_mcp.context import roots_key, verifier_for

        artifact_id = "MAT@1778000032.tmtx.matrix-stored"
        mcp.artifact_create_matrix(
            name="Matrix", matrix_markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
            artifact_id=artifact_id, dry_run=False, repo_root=str(repo),
        )
        path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "artifact-type: diagram",
                "artifact-type: diagram\nto-entity-ids:\n- OUT@9.zzz.never-created",
                1,
            ),
            encoding="utf-8",
        )

        issues = verifier_for(
            roots_key((repo.resolve(),)), include_registry=True
        ).verify_matrix_diagram_file(path)

        assert "E301" in {issue.code for issue in issues.issues}, [
            f"{i.code}: {i.message}" for i in issues.issues
        ]
        assert any("to-entity-ids" in issue.message for issue in issues.issues)

    def test_an_axis_naming_nothing_at_all_is_not_an_error(self, repo: Path) -> None:
        """A matrix may declare no axes; only a *stated* id has to resolve."""
        artifact_id = "MAT@1778000031.tmtx.matrix-no-axis"
        mcp.artifact_create_matrix(
            name="Matrix", matrix_markdown="| A | B |\n|---|---|\n| 1 | 2 |\n",
            artifact_id=artifact_id, dry_run=False, repo_root=str(repo),
        )
        path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.md"

        from src.infrastructure.mcp.artifact_mcp.context import roots_key, verifier_for

        issues = verifier_for(roots_key((repo.resolve(),)), include_registry=True).verify_matrix_diagram_file(path)

        assert not [i for i in issues.issues if i.code in ("E301", "E310")]
