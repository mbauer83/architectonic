"""The document-reference contract, held against the thing that produces it.

`GET /api/entities/{id}` answered **500** for any entity a document cites. The DTO was written from
a guess — `artifact_id` where the producer emits `document_id`, and no `label`/`href` at all — and
being closed it rejected every real reference. Nothing caught it: no unit test compared the DTO to
its producer, and no fixture in the suite had a document that cited an entity, so the only signal was
a browser spec looking for a heading that never rendered.

Two tests, because either alone leaves the gap open. The first pins the field set to the producer, so
the DTO cannot drift from what the handler serialises. The second drives the real route over a
fixture repository whose content the test owns, so the response is actually validated end to end —
a field-set comparison would still pass if the *types* diverged.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.application.document_links import DocumentEntityReference, references_to_entity
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.contracts.entities import DocumentReference
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.entities import router as entities_router

pytest.importorskip("httpx")

_ENTITY_ID = "REQ@1712870400.DocRef1.cited-requirement"
_DOCUMENT_ID = "ADR@1712870400.DocRef2.the-citing-decision"


def test_the_dto_declares_exactly_the_fields_the_producer_emits() -> None:
    """The contract is a projection of the use-case output; a name it invents is a 500 in waiting."""
    produced = DocumentEntityReference(
        document_id=_DOCUMENT_ID, title="t", doc_type="adr", path="/p",
        section="Decision", label="l", href="./x.md",
    ).to_dict()
    assert set(DocumentReference.model_fields) == set(produced)
    # And the produced dict validates, so the *types* agree too and not only the names.
    assert DocumentReference.model_validate(produced).document_id == _DOCUMENT_ID


def test_a_reference_with_an_empty_section_still_validates() -> None:
    """``section_at_offset`` returns ``""`` for a link before the first heading. The field is
    therefore always present and never null, which is why it carries no default: a default would
    publish it as omittable and let a client treat "no section" as "field missing"."""
    produced = DocumentEntityReference(
        document_id=_DOCUMENT_ID, title="t", doc_type="adr", path="/p",
        section="", label="l", href="./x.md",
    ).to_dict()
    assert DocumentReference.model_validate(produced).section == ""


@pytest.fixture()
def cited_entity_client(tmp_path: Path):
    """A repository holding one entity and one document that links to it.

    Fixture content the test owns, so the assertions below can be exact — nothing here reads the
    live repository, where authoring a new citation would change the answer.
    """
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-DOCREF" / "architecture-repository"
    entity_dir = root / "model" / "motivation" / "requirement"
    document_dir = root / "docs" / "adr"
    entity_dir.mkdir(parents=True)
    document_dir.mkdir(parents=True)

    (entity_dir / f"{_ENTITY_ID}.md").write_text(
        "---\n"
        f"artifact_id: {_ENTITY_ID}\n"
        "artifact_type: requirement\n"
        "name: Cited Requirement\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "---\n\n"
        "# Cited Requirement\n",
        encoding="utf-8",
    )
    relative = "../../model/motivation/requirement/" + _ENTITY_ID + ".md"
    # Hyphenated frontmatter keys, as the repository writes them: `parse_document` requires
    # `artifact-type: document` and a `doc-type`, and returns None for anything else — a fixture with
    # underscored keys indexes as no document at all and the citation is never found.
    (document_dir / f"{_DOCUMENT_ID}.md").write_text(
        "---\n"
        f"artifact-id: {_DOCUMENT_ID}\n"
        "artifact-type: document\n"
        "doc-type: adr\n"
        "title: The Citing Decision\n"
        "status: draft\n"
        "version: 0.1.0\n"
        "---\n\n"
        "## Decision\n\n"
        f"We adopt [the cited requirement]({relative}).\n",
        encoding="utf-8",
    )

    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = FastAPI()
    app.include_router(entities_router)
    return TestClient(app), repo


def test_the_producer_finds_the_citation_in_the_fixture(cited_entity_client) -> None:
    """Guards the fixture itself: if the link never resolved, the route test below would pass on an
    empty list and prove nothing about the contract."""
    _client, repo = cited_entity_client
    entity = repo.get_entity(_ENTITY_ID)
    assert entity is not None
    references = references_to_entity(documents=list(repo.list_documents()), entity=entity)
    assert [reference.document_id for reference in references] == [_DOCUMENT_ID]


def test_reading_a_cited_entity_returns_its_references_rather_than_a_500(
    cited_entity_client,
) -> None:
    """The regression. The response is validated against the DTO on the way out, so a field the
    contract does not declare fails the request — which is what happened, for every entity any
    document cited."""
    client, _repo = cited_entity_client
    response = client.get(f"/api/entities/{_ENTITY_ID}")
    assert response.status_code == 200, response.text
    references = response.json()["referenced_in_documents"]
    assert len(references) == 1
    reference = references[0]
    assert reference["document_id"] == _DOCUMENT_ID
    assert reference["title"] == "The Citing Decision"
    assert reference["doc_type"] == "adr"
    assert reference["section"] == "Decision"
    assert reference["label"] == "the cited requirement"
    assert reference["href"].endswith(f"{_ENTITY_ID}.md")
