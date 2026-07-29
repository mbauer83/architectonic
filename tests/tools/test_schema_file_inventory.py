"""Tests for the classified schema-file inventory: the single owner of the
``.arch-repo/schemata/`` filename conventions that startup validation, orphan detection,
and schema policy consume instead of re-parsing filenames."""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_schema import SchemaFileRef, list_schema_files


def _touch(repo_root: Path, filename: str) -> None:
    schemata_dir = repo_root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / filename).write_text("{}", encoding="utf-8")


class TestListSchemaFiles:
    def test_missing_directory_is_empty(self, tmp_path: Path) -> None:
        assert list_schema_files(tmp_path) == ()

    def test_classifies_every_convention(self, tmp_path: Path) -> None:
        for filename in (
            "attributes.requirement.schema.json",
            "attributes.requirement.constraint.schema.json",
            "connection-metadata.archimate-serving.schema.json",
            "frontmatter.entity.schema.json",
            "attributes.a.b.c.schema.json",
        ):
            _touch(tmp_path, filename)

        assert list_schema_files(tmp_path) == (
            SchemaFileRef(filename="attributes.a.b.c.schema.json", kind="unrecognized"),
            SchemaFileRef(
                filename="attributes.requirement.constraint.schema.json",
                kind="specialization-attachment", subject="requirement", specialization_slug="constraint",
            ),
            SchemaFileRef(
                filename="attributes.requirement.schema.json", kind="entity-attributes", subject="requirement"
            ),
            SchemaFileRef(
                filename="connection-metadata.archimate-serving.schema.json",
                kind="connection-metadata", subject="archimate-serving",
            ),
            SchemaFileRef(filename="frontmatter.entity.schema.json", kind="frontmatter", subject="entity"),
        )

    def test_unrelated_schema_json_is_unrecognized(self, tmp_path: Path) -> None:
        _touch(tmp_path, "something-else.schema.json")
        (ref,) = list_schema_files(tmp_path)
        assert ref.kind == "unrecognized"
        assert ref.subject == ""

    def test_empty_subject_segments_are_unrecognized(self, tmp_path: Path) -> None:
        _touch(tmp_path, "attributes..schema.json")
        _touch(tmp_path, "connection-metadata..schema.json")
        assert all(ref.kind == "unrecognized" for ref in list_schema_files(tmp_path))
