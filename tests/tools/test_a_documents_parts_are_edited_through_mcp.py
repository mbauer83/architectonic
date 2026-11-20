"""A document's parts through MCP: the rows of its typed tables read and edited, a section, a text.

An agent reads a table's rows with `artifact_query_document_tables`, changes one with
`artifact_edit_document_table` stating what it read, and is refused with the row and both values
when someone changed that row first. `artifact_edit_document` takes `section` and `replace` beside
the whole `body`. The tools take the models the REST bodies are, so the two surfaces accept one form.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.application.artifacts.document_part_edits import DocumentEditRefused, RowChangedSinceRead
from src.infrastructure.mcp import mcp_artifact_server
from src.infrastructure.mcp.artifact_mcp.write.document import artifact_edit_document, artifact_edit_document_table
from tests.support.typed_table_documents import (
    STRESS_ANALYSIS,
    document_path,
    document_text,
    document_type,
    entity_in,
    repository_in,
    table_of,
    table_text,
)


class _Authored:
    def __init__(self, tmp_path: Path) -> None:
        self.root = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        self.doc = document_path(self.root, schema)
        self.goal = entity_in(self.root, "goal", "keep-selling")
        rows = {
            "stressors": [
                {"stressor": "The provider is down", "set": "design"},
                {"stressor": "The provider doubles its fees", "set": "test"},
            ],
            "end-states": [{"end_state": "Orders cannot be paid"}],
        }
        tables = {name: table_text(table_of(schema, name), held) for name, held in rows.items()}
        content = document_text(schema, tables).replace(
            "artifact-id: DOC@1000000003.Doc.doc", f"artifact-id: {self.doc.stem}"
        )
        self.doc.parent.mkdir(parents=True, exist_ok=True)
        self.doc.write_text(
            content.replace(
                "## Naive Architecture\n", "## Naive Architecture\n\nThe shop calls the provider inline.\n"
            ),
            encoding="utf-8",
        )

    def stored(self) -> str:
        return self.doc.read_text(encoding="utf-8")

    def rows(self, table: str) -> dict[str, dict[str, Any]]:
        read = mcp_artifact_server.mcp_read._tool_manager._tools["artifact_query_document_tables"].fn
        answered = read(self.doc.stem, repo_root=str(self.root), repo_scope="engagement")
        held = next(entry for entry in answered["tables"] if entry["name"] == table)
        return {row["row_id"]: row["values"] for row in held["rows"]}

    def edit_rows(self, table: str, *rows: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        return artifact_edit_document_table(
            artifact_id=self.doc.stem,
            table=table,
            rows=list(rows),  # type: ignore[arg-type]  # as an MCP client sends them
            dry_run=dry_run,
            repo_root=str(self.root),
        )

    def edit(self, **stated: Any) -> dict[str, Any]:
        return artifact_edit_document(artifact_id=self.doc.stem, dry_run=False, repo_root=str(self.root), **stated)


@pytest.fixture()
def authored(tmp_path: Path) -> _Authored:
    return _Authored(tmp_path)


class TestRowsAreReadAndEdited:
    def test_the_rows_of_every_declared_table_are_read_as_values(self, authored: _Authored) -> None:
        assert authored.rows("stressors") == {
            "S1": {"stressor": "The provider is down", "set": "design"},
            "S2": {"stressor": "The provider doubles its fees", "set": "test"},
        }
        assert authored.rows("adaptations") == {}

    def test_a_row_is_changed_on_what_was_read_and_reads_back_changed(self, authored: _Authored) -> None:
        read = authored.rows("stressors")["S2"]

        answered = authored.edit_rows(
            "stressors", {"op": "change", "row_id": "S2", "based_on": read, "cells": {"plausible": True}}
        )

        assert (answered["wrote"], answered["added_row_ids"]) == (True, [])
        assert authored.rows("stressors")["S2"] == read | {"plausible": True}

    def test_a_row_is_added_with_a_reference_stated_as_an_id_and_another_removed(self, authored: _Authored) -> None:
        held = authored.rows("end-states")

        answered = authored.edit_rows(
            "end-states",
            {"op": "add", "cells": {"end_state": "Margins vanish", "affects": [authored.goal.stem]}},
            {"op": "remove", "row_id": "E1", "based_on": held["E1"]},
        )

        assert answered["added_row_ids"] == ["E2"]
        assert authored.rows("end-states") == {"E2": {"end_state": "Margins vanish", "affects": [authored.goal.stem]}}

    def test_a_dry_run_is_the_default_and_answers_what_it_would_write(self, authored: _Authored) -> None:
        before = authored.stored()

        answered = artifact_edit_document_table(
            artifact_id=authored.doc.stem,
            table="stressors",
            rows=[{"op": "add", "cells": {"stressor": "x", "set": "test"}}],  # type: ignore[list-item]
            repo_root=str(authored.root),
        )

        assert (answered["dry_run"], answered["wrote"], answered["added_row_ids"]) == (True, False, ["S3"])
        assert "| S3 | x | | | | test | |" in answered["content"] and authored.stored() == before

    def test_the_second_change_to_one_row_is_refused_naming_both_values(self, authored: _Authored) -> None:
        read_by_both = authored.rows("stressors")["S1"]
        authored.edit_rows(
            "stressors", {"op": "change", "row_id": "S1", "based_on": read_by_both, "cells": {"set": "test"}}
        )
        after_the_first = authored.stored()

        with pytest.raises(RowChangedSinceRead, match='row S1 has changed .* \'set\' was "design" and is now "test"'):
            authored.edit_rows(
                "stressors", {"op": "change", "row_id": "S1", "based_on": read_by_both, "cells": {"kind": "outage"}}
            )

        assert authored.stored() == after_the_first

    def test_a_change_to_another_row_meanwhile_is_written(self, authored: _Authored) -> None:
        held = authored.rows("stressors")
        authored.edit_rows(
            "stressors", {"op": "change", "row_id": "S1", "based_on": held["S1"], "cells": {"set": "test"}}
        )

        other = authored.edit_rows(
            "stressors", {"op": "change", "row_id": "S2", "based_on": held["S2"], "cells": {"kind": "market"}}
        )

        assert other["wrote"]

    def test_a_row_that_is_no_row_edit_is_refused_before_anything_is_read(self, authored: _Authored) -> None:
        with pytest.raises(ValidationError):
            authored.edit_rows("stressors", {"op": "change", "row_id": "S1", "cells": {}})

    def test_the_tool_publishes_the_three_row_edits_in_its_schema(self) -> None:
        tool = mcp_artifact_server.mcp_write._tool_manager._tools["artifact_edit_document_table"]

        schema = str(tool.parameters)
        assert all(name in schema for name in ("AddRowBody", "ChangeRowBody", "RemoveRowBody", "based_on"))


class TestASectionOrATextIsEditedThroughTheDocumentEdit:
    def test_a_section_is_replaced_and_a_link_written_by_id_is_stored_as_a_path(self, authored: _Authored) -> None:
        before = authored.stored()

        answered = authored.edit(
            section={"heading_path": ["Naive Architecture"], "text": f"It serves [the goal]({authored.goal.stem})."}
        )

        assert answered["wrote"]
        assert "It serves [the goal](../../model/goal/" in authored.stored()
        assert authored.stored().split("## Stressors", 1)[1] == before.split("## Stressors", 1)[1]

    def test_a_text_is_replaced_where_it_occurs_as_often_as_expected(self, authored: _Authored) -> None:
        assert authored.edit(replace={"find": "inline", "replacement": "queued"})["wrote"]
        assert authored.edit(replace={"find": "The provider", "replacement": "A provider", "expected_matches": 2})[
            "wrote"
        ]

        assert "calls the provider queued." in authored.stored() and authored.stored().count("A provider") == 2

    def test_another_number_of_occurrences_than_expected_is_refused(self, authored: _Authored) -> None:
        with pytest.raises(DocumentEditRefused, match="occurs 2 times in this document's body and the edit expects 1"):
            authored.edit(replace={"find": "The provider", "replacement": "x"})

    def test_a_part_beside_a_whole_body_is_refused(self, authored: _Authored) -> None:
        with pytest.raises(DocumentEditRefused, match="a whole body and a part of it"):
            authored.edit(body="## Test\n", section={"heading_path": ["Test"], "text": "x"})

    def test_the_tool_publishes_both_part_edits_in_its_schema(self) -> None:
        tool = mcp_artifact_server.mcp_write._tool_manager._tools["artifact_edit_document"]

        schema = str(tool.parameters)
        assert all(name in schema for name in ("heading_path", "expected_matches", "replacement"))
