from src.application.modeling.artifact_write_formatting import format_diagram_puml


def test_diagram_formatter_emits_format_version_when_supplied() -> None:
    content = format_diagram_puml(
        artifact_id="DT@1.ab.example",
        diagram_type="datatype",
        name="Example",
        version="0.1.0",
        status="draft",
        last_updated="2026-06-20",
        puml_body="@startuml x\n@enduml\n",
        diagram_format_version=2,
    )

    assert "diagram-format-version: 2" in content
