"""The two PATCH operations nothing exercised: a document edit, and an attribute's metadata.

`NEVER_REQUESTED_OPERATIONS` records all ten PATCH routes as never once requested through the
running server, which is §1.7's sharpest fact: 0.2.0 moved the entire partial-update surface to a new
address *and* a new method, and nothing has exercised any of it. Eight of the ten at least have
in-process coverage. Two had none at all:

* `documents_update_document` — no test issued a PATCH to `/api/documents/{artifact_id}`.
* `diagrams_update_diagram_attribute_metadata` — no test issued a PATCH to the attribute address.
  Its unit test asserts the merge helpers in isolation and says "the full patch → edit_diagram → file
  path is exercised end-to-end by the GUI Playwright smoke". The register says otherwise: the browser
  suite has never requested it. A claim about coverage, in a docstring, that the measurement
  contradicts.

Both are *round trips*: PATCH, then read back through a different route, because that is the crossing
the two worst defects of 0.2.0 came through. Asserting the mutation's own response body would only
prove the handler agrees with itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

DOC_ID = "ADR@1000000200.PatchDoc.a-decision-to-edit"
DIAGRAM_ID = "DTY@1000000201.PatchDty.types-to-annotate"
CLASSIFIER_ID = "order"
ATTRIBUTE_ID = "a_placed_at"


def _document_md() -> str:
    return f"""\
---
artifact-id: {DOC_ID}
artifact-type: adr
doc-type: adr
title: "A Decision To Edit"
version: 0.1.0
status: draft
keywords: [original]
---

## Context

The document body before the patch.

## Decision

Unchanged by a title-only patch.
"""


def _datatype_diagram_puml() -> str:
    """A datatype diagram with one classifier carrying one attribute.

    The attribute is what the uncovered route addresses, so the fixture has to reach that depth —
    `/api/diagrams/{id}/entities/{classifier}/attributes/{attribute}/metadata` names three levels of
    identity, which is the reason this route is the fiddliest of the ten and, plausibly, the reason
    nothing had called it.
    """
    return f"""\
---
artifact-id: {DIAGRAM_ID}
artifact-type: diagram
diagram-type: datatype
name: "Types To Annotate"
version: 0.1.0
status: draft
diagram-entities:
  classifier:
    - id: {CLASSIFIER_ID}
      label: Order
      kind: entity
      attributes:
        - id: {ATTRIBUTE_ID}
          name: placed_at
          type:
            kind: primitive
            name: DateTime
---
@startuml
class Order {{
  placed_at: DateTime
}}
@enduml
"""


#: The document-type schema a real repository declares. Without it the write is *refused* — `E153
#: Unknown doc-type 'adr': no schema at .arch-repo/documents/adr.json` — and the route answers 200
#: with `wrote: false` and the verification attached. Which is correct behaviour and a good reminder
#: that a fixture repository is not just files in the right folders.
_ADR_SCHEMA = """\
{
  "abbreviation": "ADR",
  "name": "Architecture Decision Record",
  "required_sections": ["Context", "Decision"]
}
"""


@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-PATCH" / "architecture-repository"
    schema_path = root / ".arch-repo" / "documents" / "adr.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(_ADR_SCHEMA, encoding="utf-8")
    doc_dir = root / "docs" / "adr" / "uncategorized"
    doc_dir.mkdir(parents=True)
    (doc_dir / f"{DOC_ID}.md").write_text(_document_md(), encoding="utf-8")
    diagram_dir = root / "diagram-catalog" / "diagrams"
    diagram_dir.mkdir(parents=True)
    (diagram_dir / f"{DIAGRAM_ID}.puml").write_text(_datatype_diagram_puml(), encoding="utf-8")
    (root / "model").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def client(populated_root: Path) -> Any:
    from starlette.testclient import TestClient

    from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
    from src.infrastructure.rest.routers.documents import router as documents_router

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    return TestClient(build_api_app(documents_router, diagrams_router))


class TestDocumentPatchRoundTrip:
    def test_a_title_patch_is_visible_to_the_next_read(self, client: Any) -> None:
        response = client.patch(f"/api/documents/{DOC_ID}", json={"title": "A Decision, Edited", "dry_run": False})
        assert response.status_code == 200, response.text
        assert response.json()["wrote"] is True

        read_back = client.get(f"/api/documents/{DOC_ID}")
        assert read_back.status_code == 200, read_back.text
        assert read_back.json()["title"] == "A Decision, Edited"

    def test_a_patch_leaves_the_fields_it_does_not_name(self, client: Any) -> None:
        """The definition of a partial update, and the reason `PUT` was the wrong method for it.

        A `PUT` states what the resource becomes; this states a delta. If the body were treated as a
        replacement, the keywords and the body text would be gone — and nothing would have noticed,
        because the mutation's own response reports success either way.
        """
        client.patch(f"/api/documents/{DOC_ID}", json={"title": "Only The Title Moved", "dry_run": False})
        body = client.get(f"/api/documents/{DOC_ID}").json()
        assert body["keywords"] == ["original"]
        assert "The document body before the patch." in body["content_text"]

    def test_a_patch_of_the_body_reaches_the_file(self, client: Any, populated_root: Path) -> None:
        response = client.patch(
            f"/api/documents/{DOC_ID}",
            json={
                "body": "## Context\n\nRewritten by the patch.\n\n## Decision\n\nStill this.\n",
                "dry_run": False,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["wrote"] is True, response.text
        stored = (populated_root / "docs" / "adr" / "uncategorized" / f"{DOC_ID}.md").read_text(
            encoding="utf-8"
        )
        assert "Rewritten by the patch." in stored

    def test_a_body_missing_a_required_section_is_not_written(
        self, client: Any, populated_root: Path
    ) -> None:
        """The document schema's `required_sections`, enforced on a partial update.

        Worth its own test because the refusal arrives as `wrote: false` inside a **200**, with the
        reason in `verification.issues` — not as a 4xx. A caller that checks only the status code
        reads this as success, which is how my own first version of the test above concluded the
        route was broken: the body it sent omitted `## Decision`, the write was correctly refused,
        and the 200 said nothing about it.
        """
        response = client.patch(
            f"/api/documents/{DOC_ID}",
            json={"body": "## Context\n\nNo decision section.\n", "dry_run": False},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["wrote"] is False
        assert body["verification"]["valid"] is False
        stored = (populated_root / "docs" / "adr" / "uncategorized" / f"{DOC_ID}.md").read_text(
            encoding="utf-8"
        )
        assert "No decision section." not in stored

    def test_a_patch_naming_no_field_is_a_no_op_that_still_verifies(self, client: Any) -> None:
        """An empty delta rewrites nothing and says so, rather than being refused.

        Recorded rather than asserted-against: the route answers 200 with `wrote: true` and a
        `content: null`, having touched the file's modification stamp and re-verified it. That is a
        defensible reading of "apply this empty delta" and it is what the surface does; a 400 would
        be equally defensible. What matters for a caller is that it is *stated*, because the previous
        state of this route was that nobody knew which it did.
        """
        response = client.patch(f"/api/documents/{DOC_ID}", json={"dry_run": False})
        assert response.status_code == 200, response.text
        assert response.json()["verification"]["valid"] is True

    def test_patching_a_document_that_does_not_exist_is_a_not_found(self, client: Any) -> None:
        response = client.patch(
            "/api/documents/ADR@1000000299.Missing.no-such-decision", json={"title": "x", "dry_run": False}
        )
        assert response.status_code == 404, response.text


class TestAttributeMetadataPatchRoundTrip:
    """The three-level address: diagram → classifier → attribute.

    Read back through the diagram's own read route rather than trusting the write's answer, because
    the metadata lives inside the diagram's `diagram-entities` frontmatter and the whole question is
    whether the merge reached the file.
    """

    def _stored_attribute(self, populated_root: Path) -> dict[str, Any]:
        text = (populated_root / "diagram-catalog" / "diagrams" / f"{DIAGRAM_ID}.puml").read_text(
            encoding="utf-8"
        )
        frontmatter = yaml.safe_load(text.split("---\n")[1])
        classifiers = frontmatter["diagram-entities"]["classifier"]
        attributes = next(c for c in classifiers if c["id"] == CLASSIFIER_ID)["attributes"]
        return next(a for a in attributes if a["id"] == ATTRIBUTE_ID)

    def _address(self) -> str:
        return (
            f"/api/diagrams/{DIAGRAM_ID}/entities/{CLASSIFIER_ID}"
            f"/attributes/{ATTRIBUTE_ID}/metadata"
        )

    def test_a_metadata_patch_reaches_the_attribute_in_the_file(
        self, client: Any, populated_root: Path
    ) -> None:
        response = client.patch(
            self._address(), json={"patch": {"multiplicity": "0..1", "note": "nullable on import"}, "dry_run": False}
        )
        assert response.status_code == 200, response.text
        assert response.json()["wrote"] is True

        stored = self._stored_attribute(populated_root)
        assert stored["multiplicity"] == "0..1"
        assert stored["note"] == "nullable on import"

    def test_the_patch_leaves_the_attribute_type_alone(
        self, client: Any, populated_root: Path
    ) -> None:
        # The whitelist is meta-only by construction: a metadata patch must not be a way to retype an
        # attribute, which would change what the model *means* through a route named for annotation.
        client.patch(self._address(), json={"patch": {"note": "annotated"}, "dry_run": False})
        stored = self._stored_attribute(populated_root)
        assert stored["type"] == {"kind": "primitive", "name": "DateTime"}

    def test_a_field_outside_the_whitelist_is_refused(self, client: Any) -> None:
        response = client.patch(
            self._address(),
            json={"patch": {"type": {"kind": "primitive", "name": "String"}}, "dry_run": False},
        )
        assert response.status_code in (400, 422), response.text

    def test_an_unknown_attribute_is_a_not_found_rather_than_a_silent_success(
        self, client: Any
    ) -> None:
        response = client.patch(
            f"/api/diagrams/{DIAGRAM_ID}/entities/{CLASSIFIER_ID}/attributes/no_such/metadata",
            json={"patch": {"note": "x"}, "dry_run": False},
        )
        assert response.status_code in (400, 404), response.text

    def test_an_unknown_classifier_is_a_not_found(self, client: Any) -> None:
        response = client.patch(
            f"/api/diagrams/{DIAGRAM_ID}/entities/no_such/attributes/{ATTRIBUTE_ID}/metadata",
            json={"patch": {"note": "x"}, "dry_run": False},
        )
        assert response.status_code in (400, 404), response.text

    def test_a_dry_run_reports_what_it_would_do_and_writes_nothing(
        self, client: Any, populated_root: Path
    ) -> None:
        # No flag: planning is what omitting it means now, on all twenty-nine write operations.
        response = client.patch(self._address(), json={"patch": {"note": "considered"}})
        assert response.status_code == 200, response.text
        assert response.json()["wrote"] is False
        assert "note" not in self._stored_attribute(populated_root)
