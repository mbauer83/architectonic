"""A document's parts over REST: a section, a text, and the rows of its typed tables.

Three operations. `PATCH /api/documents/{id}` takes `section` and `replace` beside the whole `body`
it always took; `GET /api/documents/{id}/tables` serves each declared table's rows as values; and
`PATCH /api/documents/{id}/tables/{table}` adds, changes and removes rows by id. A client reads a
row's values, sends them back as what its change is based on, and is told with a 409 when another
writer changed that row first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.documents import router as documents_router
from tests.support.api_app import build_api_app
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

httpx = pytest.importorskip("httpx")


class _Served:
    def __init__(self, tmp_path: Path) -> None:
        from starlette.testclient import TestClient

        self.root = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        self.doc = document_path(self.root, schema)
        self.goal = entity_in(self.root, "goal", "keep-selling")
        rows = {
            "stressors": [
                {"stressor": "The provider is down", "set": "design", "plausible": "true"},
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
        gui_state.init_state(ArtifactRepository(shared_artifact_index([self.root])), self.root, None)
        self.client = TestClient(build_api_app(documents_router))
        self.url = f"/api/documents/{self.doc.stem}"

    def stored(self) -> str:
        return self.doc.read_text(encoding="utf-8")

    def rows(self, table: str) -> dict[str, dict[str, Any]]:
        response = self.client.get(f"{self.url}/tables")
        assert response.status_code == 200, response.text
        held = next(entry for entry in response.json()["tables"] if entry["name"] == table)
        return {row["row_id"]: row["values"] for row in held["rows"]}

    def edit_rows(self, table: str, *rows: dict[str, Any], dry_run: bool = False) -> Any:
        return self.client.patch(f"{self.url}/tables/{table}", json={"rows": list(rows), "dry_run": dry_run})


@pytest.fixture()
def served(tmp_path: Path) -> _Served:
    return _Served(tmp_path)


class TestTheRowsOfADocumentsTablesAreServedAsValues:
    def test_every_declared_table_with_each_rows_id_and_typed_values(self, served: _Served) -> None:
        response = served.client.get(f"{served.url}/tables")

        assert response.status_code == 200, response.text
        tables = {entry["name"]: entry for entry in response.json()["tables"]}
        assert list(tables) == ["stressors", "end-states", "adaptations", "incidence", "survival"]
        assert tables["stressors"] == {
            "name": "stressors",
            "section": "Stressors",
            "found": True,
            "missing_columns": [],
            "undeclared_columns": [],
            "rows": [
                {
                    "row_id": "S1",
                    "unreadable": {},
                    "values": {"stressor": "The provider is down", "set": "design", "plausible": True},
                },
                {
                    "row_id": "S2",
                    "unreadable": {},
                    "values": {"stressor": "The provider doubles its fees", "set": "test"},
                },
            ],
        }
        assert tables["adaptations"]["rows"] == []

    def test_a_cell_that_cannot_be_read_is_served_as_spelled_with_the_reason(self, served: _Served) -> None:
        served.doc.write_text(served.stored().replace("| true |", "| likely |"), encoding="utf-8")

        (first, _) = next(
            e for e in served.client.get(f"{served.url}/tables").json()["tables"] if e["name"] == "stressors"
        )["rows"]

        assert first["values"]["plausible"] == "likely"
        assert "Cannot decode 'likely' as boolean" in first["unreadable"]["plausible"]

    def test_a_document_that_is_not_there_is_a_404(self, served: _Served) -> None:
        assert served.client.get("/api/documents/STRESS@1.none.none/tables").status_code == 404


class TestRowsAreEditedById:
    def test_a_row_read_is_changed_on_what_was_read_and_reads_back_changed(self, served: _Served) -> None:
        read = served.rows("stressors")["S2"]

        response = served.edit_rows(
            "stressors",
            {"op": "change", "row_id": "S2", "based_on": read, "cells": {"plausible": False, "kind": "market"}},
        )

        assert response.status_code == 200, response.text
        assert (response.json()["wrote"], response.json()["added_row_ids"]) == (True, [])
        assert served.rows("stressors")["S2"] == read | {"plausible": False, "kind": "market"}

    def test_rows_are_added_removed_and_changed_in_one_request(self, served: _Served) -> None:
        held = served.rows("stressors")

        response = served.edit_rows(
            "stressors",
            {"op": "add", "cells": {"stressor": "A third", "set": "test"}},
            {"op": "remove", "row_id": "S1", "based_on": held["S1"]},
            {"op": "change", "row_id": "S2", "based_on": held["S2"], "cells": {"set": "design"}},
        )

        assert response.status_code == 200, response.text
        assert response.json()["added_row_ids"] == ["S3"]
        assert served.rows("stressors") == {
            "S2": {"stressor": "The provider doubles its fees", "set": "design"},
            "S3": {"stressor": "A third", "set": "test"},
        }

    def test_a_reference_is_written_as_an_artifact_id_and_read_back_as_one(self, served: _Served) -> None:
        read = served.rows("end-states")["E1"]

        response = served.edit_rows(
            "end-states", {"op": "change", "row_id": "E1", "based_on": read, "cells": {"affects": [served.goal.stem]}}
        )

        assert response.status_code == 200 and response.json()["wrote"], response.text
        assert served.rows("end-states")["E1"] == read | {"affects": [served.goal.stem]}
        assert "| [keep-selling](../../model/goal/" in served.stored()

    def test_a_dry_run_is_the_default_and_writes_nothing(self, served: _Served) -> None:
        before = served.stored()

        response = served.client.patch(
            f"{served.url}/tables/stressors", json={"rows": [{"op": "add", "cells": {"stressor": "x", "set": "test"}}]}
        )

        assert response.status_code == 200, response.text
        assert (response.json()["wrote"], response.json()["added_row_ids"]) == (False, ["S3"])
        assert "| S3 | x | | | | test | |" in response.json()["content"]
        assert served.stored() == before


class TestWhatIsRefusedAndWithWhichStatus:
    def test_a_row_another_writer_changed_first_is_a_conflict_naming_both_values(self, served: _Served) -> None:
        read_by_both = served.rows("stressors")["S1"]
        first = {"op": "change", "row_id": "S1", "based_on": read_by_both, "cells": {"set": "test"}}
        assert served.edit_rows("stressors", first).status_code == 200
        after_the_first = served.stored()

        second = served.edit_rows(
            "stressors", {"op": "change", "row_id": "S1", "based_on": read_by_both, "cells": {"kind": "outage"}}
        )

        assert second.status_code == 409, second.text
        assert (
            'row S1 has changed since it was read: \'set\' was "design" and is now "test"'
            in second.json()["detail"]["message"]
        )
        assert served.stored() == after_the_first

    def test_a_change_to_another_row_meanwhile_is_no_conflict(self, served: _Served) -> None:
        held = served.rows("stressors")
        assert (
            served.edit_rows(
                "stressors", {"op": "change", "row_id": "S1", "based_on": held["S1"], "cells": {"set": "test"}}
            ).status_code
            == 200
        )

        other = served.edit_rows(
            "stressors", {"op": "change", "row_id": "S2", "based_on": held["S2"], "cells": {"kind": "market"}}
        )

        assert other.status_code == 200 and other.json()["wrote"], other.text

    @pytest.mark.parametrize(
        ("table", "row", "status", "said"),
        [
            ("stressors", {"op": "remove", "row_id": "S9", "based_on": {}}, 400, "holds no row 'S9'"),
            ("nope", {"op": "add", "cells": {}}, 400, "declares no table 'nope'"),
            ("stressors", {"op": "add", "cells": {"nope": "x"}}, 400, "declares no column 'nope'"),
            (
                "end-states",
                {"op": "add", "cells": {"required_behaviour": "REQ@1.gone"}},
                400,
                "REQ@1.gone: no artifact",
            ),
            ("stressors", {"op": "rename", "row_id": "S1"}, 422, ""),
            ("stressors", {"op": "change", "row_id": "S1", "cells": {}}, 422, ""),
        ],
    )
    def test_an_edit_that_cannot_be_made(
        self, served: _Served, table: str, row: dict[str, Any], status: int, said: str
    ) -> None:
        before = served.stored()

        response = served.edit_rows(table, row)

        assert response.status_code == status, response.text
        assert said in response.text and served.stored() == before

    def test_a_cell_that_cannot_be_read_is_not_written_and_the_finding_is_answered(self, served: _Served) -> None:
        before = served.stored()

        response = served.edit_rows(
            "stressors", {"op": "add", "cells": {"stressor": "x", "set": "test", "plausible": "likely"}}
        )

        assert response.status_code == 200, response.text
        assert response.json()["wrote"] is False and served.stored() == before
        assert [issue["code"] for issue in response.json()["verification"]["issues"]] == ["E162"]

    def test_a_document_that_is_not_there_is_a_404(self, served: _Served) -> None:
        response = served.client.patch(
            "/api/documents/STRESS@1.none.none/tables/stressors", json={"rows": [{"op": "add", "cells": {}}]}
        )

        assert response.status_code == 404, response.text


class TestASectionOrATextIsEditedThroughTheDocumentEdit:
    def test_a_section_is_replaced_by_its_heading_path(self, served: _Served) -> None:
        before = served.stored()

        response = served.client.patch(
            served.url,
            json={
                "section": {
                    "heading_path": ["Naive Architecture"],
                    "text": f"It serves [](GOL-is-not-an-id) and [the goal]({served.goal.stem}).",
                },
                "dry_run": False,
            },
        )

        assert response.status_code == 200 and response.json()["wrote"], response.text
        after = served.stored()
        assert "It serves [](GOL-is-not-an-id) and [the goal](../../model/goal/" in after
        assert after.split("## Stressors", 1)[1] == before.split("## Stressors", 1)[1]

    def test_a_text_is_replaced_where_it_occurs_as_often_as_expected(self, served: _Served) -> None:
        once = served.client.patch(
            served.url, json={"replace": {"find": "inline", "replacement": "queued"}, "dry_run": False}
        )
        twice = served.client.patch(
            served.url,
            json={
                "replace": {"find": "The provider", "replacement": "A provider", "expected_matches": 2},
                "dry_run": False,
            },
        )

        assert (once.status_code, twice.status_code) == (200, 200), (once.text, twice.text)
        assert "calls the provider queued." in served.stored() and served.stored().count("A provider") == 2

    @pytest.mark.parametrize(
        ("body", "status", "said"),
        [
            ({"replace": {"find": "The provider", "replacement": "x"}}, 400, "occurs 2 times"),
            ({"section": {"heading_path": ["Nope"], "text": "x"}}, 400, "no heading 'Nope'"),
            ({"section": {"heading_path": ["Test"], "text": "x"}, "body": "## Test\n"}, 400, "a whole body and a part"),
            (
                {"section": {"heading_path": ["Test"], "text": "x"}, "replace": {"find": "a", "replacement": "b"}},
                400,
                "a section and a replacement",
            ),
            ({"section": {"heading_path": [], "text": "x"}}, 422, ""),
            ({"replace": {"find": "", "replacement": "x"}}, 422, ""),
        ],
    )
    def test_a_part_edit_that_cannot_be_made(
        self, served: _Served, body: dict[str, Any], status: int, said: str
    ) -> None:
        before = served.stored()

        response = served.client.patch(served.url, json=body | {"dry_run": False})

        assert response.status_code == status, response.text
        assert said in response.text and served.stored() == before
