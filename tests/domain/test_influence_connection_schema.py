from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA


def test_influence_polarity_is_an_optional_shipped_relationship_property() -> None:
    schema = DEFAULT_SCHEMATA["connection-metadata.archimate-influence.schema.json"]
    assert schema["required"] == []
    assert schema["properties"]["polarity"]["enum"] == ["positive", "negative"]
