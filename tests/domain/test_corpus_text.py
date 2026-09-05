"""What a record is encoded as, stated over the syntax the decision permits rather than one fixture.

Two records that differ only in an identifier must encode identically, and a record with no words
must produce nothing to encode. Both are properties of the corpus rather than of any one record, so
they are asserted as properties.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.corpus_text import CHUNK_CHARACTERS, embeddable_text, text_chunks
from src.domain.ontology_representation.artifact_types import (
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)


def _entity(**overrides: object) -> EntityRecord:
    defaults: dict[str, object] = {
        "artifact_id": "FNC@1000000001.aaaaaa.fuse-ranked-results",
        "artifact_type": "function",
        "name": "Fuse Ranked Results",
        "version": "0.1.0",
        "status": "active",
        "domain": "application",
        "subdomain": "",
        "path": Path("/nowhere.md"),
        "keywords": ("search", "ranking"),
        "extra": {},
        "content_text": "Combine what several retrievers found into one list.",
        "display_blocks": {},
        "display_label": "Fuse Ranked Results",
        "display_alias": "FNC_aaaaaa",
    }
    return EntityRecord(**{**defaults, **overrides})  # type: ignore[arg-type]


def _document(**overrides: object) -> DocumentRecord:
    defaults: dict[str, object] = {
        "artifact_id": "ADR@1000000002.bbbbbb.embedding-locally",
        "doc_type": "adr",
        "title": "Embedding Locally",
        "status": "accepted",
        "path": Path("/nowhere.md"),
        "keywords": ("embedding",),
        "sections": ("Context",),
        "content_text": "Vectors come from a static model held within the deployment.",
        "extra": {},
    }
    return DocumentRecord(**{**defaults, **overrides})  # type: ignore[arg-type]


def _diagram() -> DiagramRecord:
    return DiagramRecord(
        artifact_id="ARC@1000000003.cccccc.querying-navigation",
        artifact_type="diagram",
        name="Querying and Navigation",
        diagram_type="archimate-layered",
        version="0.1.0",
        status="draft",
        path=Path("/nowhere.puml"),
        extra={},
    )


# ── what a record contributes ────────────────────────────────────────────────


def test_an_entity_contributes_its_name_kind_keywords_and_prose() -> None:
    text = embeddable_text(_entity())
    for expected in ("Fuse Ranked Results", "function", "search", "Combine what several retrievers"):
        assert expected in text


def test_a_document_contributes_its_title_kind_keywords_and_prose() -> None:
    text = embeddable_text(_document())
    for expected in ("Embedding Locally", "adr", "embedding", "static model"):
        assert expected in text


def test_a_diagram_contributes_what_it_has() -> None:
    """A diagram record carries no body; it is still worth a vector for its name."""
    text = embeddable_text(_diagram())
    assert "Querying and Navigation" in text
    assert "archimate-layered" in text


def test_identifiers_are_left_out_of_every_kind() -> None:
    """An id resembles every other id, which is the noise mean-pooling is worst at ignoring."""
    for record in (_entity(), _document(), _diagram()):
        assert record.artifact_id not in embeddable_text(record)


def test_two_records_differing_only_by_identifier_encode_identically() -> None:
    assert embeddable_text(_entity()) == embeddable_text(
        _entity(artifact_id="FNC@9999999999.zzzzzz.something-else")
    )


def test_a_record_with_no_prose_still_yields_its_name() -> None:
    assert embeddable_text(_entity(content_text="", keywords=())) .startswith("Fuse Ranked Results")


def test_a_record_with_nothing_at_all_yields_no_chunks() -> None:
    """Nothing should index a vector for a passage with no words in it."""
    empty = _entity(name="", content_text="", keywords=(), artifact_type="")
    assert text_chunks(embeddable_text(empty)) == ()


# ── chunking ─────────────────────────────────────────────────────────────────


def test_a_short_record_is_one_chunk() -> None:
    assert len(text_chunks("a handful of words")) == 1


def test_a_long_passage_splits_at_about_the_chunk_size() -> None:
    text = " ".join(["word"] * 400)  # ~2000 characters
    chunks = text_chunks(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= CHUNK_CHARACTERS for chunk in chunks)


def test_no_chunk_boundary_falls_inside_a_word() -> None:
    text = " ".join(f"token{index:04d}" for index in range(300))
    for chunk in text_chunks(text):
        for word in chunk.split():
            assert word in text.split()


def test_chunking_loses_no_words() -> None:
    text = " ".join(f"w{index}" for index in range(500))
    assert " ".join(text_chunks(text)).split() == text.split()


def test_a_single_word_longer_than_a_chunk_overruns_rather_than_being_cut() -> None:
    """Half a token encodes as something the whole one does not resemble."""
    monster = "x" * (CHUNK_CHARACTERS * 2)
    assert text_chunks(monster) == (monster,)


def test_whitespace_only_text_yields_no_chunks() -> None:
    assert text_chunks("   \n\t  ") == ()
