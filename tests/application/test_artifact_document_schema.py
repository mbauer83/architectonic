from __future__ import annotations

import json
from pathlib import Path

from src.application.artifact_document_schema import (
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
    assert schema.sections[0].required_entity_type_connections == ("requirement",)
    assert schema.sections[0].suggested_entity_type_connections == ("principle", "@all")
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
    assert loaded.sections[0].required_entity_type_connections == ("requirement",)
