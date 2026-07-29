from src.domain.diagrams.diagram_type_config import diagram_type_ui_config_from_mapping


def test_diagram_owned_types_are_hidden_from_global_search_by_default() -> None:
    config = diagram_type_ui_config_from_mapping(
        {"ui": {"diagram_only_types": [{"entity_type": "note", "label": "Note"}]}},
        default_label="Test",
    )
    assert config.diagram_only_types[0].include_in_global_search is False


def test_diagram_owned_type_can_opt_into_global_search() -> None:
    config = diagram_type_ui_config_from_mapping(
        {
            "ui": {
                "diagram_only_types": [
                    {"entity_type": "note", "label": "Note", "include_in_global_search": True}
                ]
            }
        },
        default_label="Test",
    )
    assert config.diagram_only_types[0].include_in_global_search is True
