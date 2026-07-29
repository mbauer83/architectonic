"""Tests for connection-type metadata parsing in diagram_ontology_loader.

Verifies that _parse_connection_types surfaces classes, symmetric, puml_arrow,
and show_stereotype on ConnectionTypeInfo (fields were previously left at their
defaults regardless of what the YAML declared).
"""

from __future__ import annotations

from pathlib import Path

from src.domain.diagrams.diagram_ontology_loader import load_diagram_ontology


def _write_ontology(tmp_path: Path, yaml_text: str) -> Path:
    f = tmp_path / "ontology.yaml"
    f.write_text(yaml_text, encoding="utf-8")
    return f


class TestConnectionTypeMetadataParsing:
    def test_classes_populated_from_yaml(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-assoc:\n    embedding: none\n    classes: [structural, reversible]\n",
        )
        ont = load_diagram_ontology(path)
        info = ont.connection_types["dt-assoc"]
        assert "structural" in info.classes
        assert "reversible" in info.classes

    def test_symmetric_true_parsed(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-assoc:\n    embedding: none\n    symmetric: true\n",
        )
        ont = load_diagram_ontology(path)
        assert ont.connection_types["dt-assoc"].symmetric is True

    def test_symmetric_defaults_false(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-gen:\n    embedding: none\n",
        )
        ont = load_diagram_ontology(path)
        assert ont.connection_types["dt-gen"].symmetric is False

    def test_puml_arrow_parsed(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-gen:\n    embedding: none\n    puml_arrow: \"--|>\"\n",
        )
        ont = load_diagram_ontology(path)
        assert ont.connection_types["dt-gen"].puml_arrow == "--|>"

    def test_puml_arrow_defaults_to_standard_arrow(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-dep:\n    embedding: none\n",
        )
        ont = load_diagram_ontology(path)
        assert ont.connection_types["dt-dep"].puml_arrow == "-->"

    def test_show_stereotype_false_parsed(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-assoc:\n    embedding: none\n    show_stereotype: false\n",
        )
        ont = load_diagram_ontology(path)
        assert ont.connection_types["dt-assoc"].show_stereotype is False

    def test_show_stereotype_defaults_true(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-assoc:\n    embedding: none\n",
        )
        ont = load_diagram_ontology(path)
        assert ont.connection_types["dt-assoc"].show_stereotype is True

    def test_all_fields_together(self, tmp_path: Path) -> None:
        yaml_text = (
            "connection_types:\n"
            "  dt-association:\n"
            "    embedding: none\n"
            "    classes: [structural]\n"
            "    symmetric: true\n"
            "    puml_arrow: \"--\"\n"
            "    show_stereotype: false\n"
        )
        path = _write_ontology(tmp_path, yaml_text)
        ont = load_diagram_ontology(path)
        info = ont.connection_types["dt-association"]
        assert info.classes == ("structural",)
        assert info.symmetric is True
        assert info.puml_arrow == "--"
        assert info.show_stereotype is False

    def test_existing_fields_unaffected(self, tmp_path: Path) -> None:
        yaml_text = (
            "connection_types:\n"
            "  embed-conn:\n"
            "    embedding: array\n"
            "    embed_key: items\n"
            "    cascade_delete_source: true\n"
        )
        path = _write_ontology(tmp_path, yaml_text)
        ont = load_diagram_ontology(path)
        info = ont.connection_types["embed-conn"]
        assert info.embedding == "array"
        assert info.embed_key == "items"
        assert info.cascade_delete_source is True
        assert info.classes == ()
        assert info.symmetric is False

    def test_empty_classes_list(self, tmp_path: Path) -> None:
        path = _write_ontology(
            tmp_path,
            "connection_types:\n  dt-dep:\n    embedding: none\n    classes: []\n",
        )
        ont = load_diagram_ontology(path)
        assert ont.connection_types["dt-dep"].classes == ()
