from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.artifacts.document_schema import (
    get_document_schema,
    get_document_schema_object,
    normalize_document_schema,
)


def _write_schema(repo_root: Path, doc_type: str, data: dict[str, object]) -> None:
    schema_dir = repo_root / ".arch-repo" / "documents"
    schema_dir.mkdir(parents=True)
    (schema_dir / f"{doc_type}.json").write_text(json.dumps(data), encoding="utf-8")


def test_normalize_legacy_required_sections_and_templates() -> None:
    schema = normalize_document_schema(
        "standard",
        {
            "name": "Standard",
            "required_sections": ["Scope", "Specification"],
            "section_templates": {"Scope": "State scope.\n"},
            "required_entity_type_connections": ["requirement"],
        },
    )

    assert schema.required_sections == ("Scope", "Specification")
    assert schema.section_templates == {"Scope": "State scope.\n"}
    assert [section.name for section in schema.sections] == ["Scope", "Specification"]
    assert schema.sections[0].template == "State scope.\n"
    assert schema.sections[1].template is None


@pytest.mark.verifies("REQ@1777369067.3cJ1Yi")
def test_normalize_sections_shape_preserves_per_section_rules() -> None:
    schema = normalize_document_schema(
        "standard",
        {
            "name": "Standard",
            "sections": [
                {
                    "name": "Scope",
                    "template": "State scope.\n",
                    "required_entity_type_connections": ["requirement"],
                    "suggested_entity_type_connections": ["principle", "@all"],
                },
                {"name": "Specification"},
            ],
        },
    )

    assert schema.required_sections == ("Scope", "Specification")
    assert schema.sections[0].required_connections == ("requirement",)
    assert schema.sections[0].suggested_connections == ("principle", "@all")
    assert schema.to_dict()["required_sections"] == ["Scope", "Specification"]
    assert schema.to_dict()["section_templates"] == {"Scope": "State scope.\n"}


def test_loader_returns_legacy_compatible_dict_with_sections(tmp_path: Path) -> None:
    _write_schema(
        tmp_path,
        "adr",
        {
            "name": "ADR",
            "required_sections": ["Context", "Decision"],
            "section_templates": {"Decision": "Decision text.\n"},
        },
    )

    loaded = get_document_schema(tmp_path, "adr")
    assert loaded is not None
    assert loaded["required_sections"] == ["Context", "Decision"]
    assert loaded["section_templates"] == {"Decision": "Decision text.\n"}
    assert loaded["sections"] == [
        {"name": "Context"},
        {"name": "Decision", "template": "Decision text.\n"},
    ]


@pytest.mark.verifies("REQ@1777369067.3cJ1Yi")
def test_loader_exposes_typed_document_schema(tmp_path: Path) -> None:
    _write_schema(
        tmp_path,
        "standard",
        {
            "name": "Standard",
            "sections": [
                {"name": "Scope", "required_entity_type_connections": ["requirement"]},
            ],
        },
    )

    loaded = get_document_schema_object(tmp_path, "standard")
    assert loaded is not None
    assert loaded.required_sections == ("Scope",)
    assert loaded.sections[0].required_connections == ("requirement",)


# ---------------------------------------------------------------------------
# The widened connection vocabulary, and the spelling it replaced
# ---------------------------------------------------------------------------


def test_legacy_entity_only_keys_normalize_to_the_widened_fields() -> None:
    """A schema written before document and diagram types joined the vocabulary reads unchanged.

    The old spelling is accepted at the loader and nowhere else, so there stays one declaration
    reader — the alternative is every consumer checking both keys, which is how the entity-only pair
    came to be named at thirteen sites.
    """
    schema = normalize_document_schema(
        "standard",
        {
            "name": "Standard",
            "sections": [
                {
                    "name": "Specification",
                    "required_entity_type_connections": ["requirement"],
                    "suggested_entity_type_connections": ["principle"],
                }
            ],
            "required_entity_type_connections": ["outcome"],
            "suggested_entity_type_connections": ["@all"],
        },
    )

    assert schema.required_connections == ("outcome",)
    assert schema.suggested_connections == ("@all",)
    assert schema.sections[0].required_connections == ("requirement",)
    assert schema.sections[0].suggested_connections == ("principle",)


def test_the_legacy_keys_are_never_emitted_again() -> None:
    schema = normalize_document_schema(
        "standard",
        {"name": "Standard", "sections": [{"name": "Scope"}], "required_entity_type_connections": ["requirement"]},
    )

    emitted = schema.to_dict()

    assert emitted["required_connections"] == ["requirement"]
    assert "required_entity_type_connections" not in emitted


def test_both_spellings_are_read_rather_than_one_winning() -> None:
    """A schema part-way through being rewritten would otherwise silently lose one of its lists."""
    schema = normalize_document_schema(
        "standard",
        {
            "name": "Standard",
            "sections": [{"name": "Scope"}],
            "required_connections": ["doc:adr"],
            "required_entity_type_connections": ["requirement"],
        },
    )

    assert schema.required_connections == ("doc:adr", "requirement")


def test_widened_terms_survive_the_load_round_trip(tmp_path: Path) -> None:
    _write_schema(
        tmp_path,
        "arch",
        {
            "name": "Architecture",
            "sections": [
                {"name": "Context", "required_connections": ["diagram:c4-system-context", "doc:adr"]}
            ],
            "suggested_connections": ["doc:@all"],
        },
    )

    loaded = get_document_schema_object(tmp_path, "arch")
    assert loaded is not None
    assert loaded.sections[0].required_connections == ("diagram:c4-system-context", "doc:adr")
    assert loaded.suggested_connections == ("doc:@all",)

    served = get_document_schema(tmp_path, "arch")
    assert served is not None
    assert served["sections"][0]["required_connections"] == ["diagram:c4-system-context", "doc:adr"]
    assert served["suggested_connections"] == ["doc:@all"]


@pytest.mark.parametrize(
    "terms",
    [
        ["requirement"],
        ["@all"],
        ["@internal-behavior-element"],
        ["doc:adr"],
        ["doc:@all"],
        ["diagram:c4-container"],
        ["diagram:@all"],
        ["requirement", "doc:adr", "diagram:matrix", "@internal-behavior-element"],
    ],
)
def test_the_term_syntax_survives_the_write_read_round_trip(terms: list[str]) -> None:
    """The pair, not each side against a fixture.

    Stated over what the syntax *permits* rather than what the shipped schemata happen to declare
    today: the last gate of this shape passed against a broken reading because the catalogue in the
    box exercised none of the interesting cases.
    """
    written = normalize_document_schema(
        "arch",
        {
            "name": "Architecture",
            "sections": [{"name": "Context", "required_connections": terms}],
            "suggested_connections": terms,
        },
    ).to_dict()

    read_back = normalize_document_schema("arch", written)

    assert list(read_back.sections[0].required_connections) == terms
    assert list(read_back.suggested_connections) == terms
    assert read_back.to_dict() == written
