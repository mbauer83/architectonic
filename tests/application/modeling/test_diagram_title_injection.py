"""A user-controlled diagram name must not be able to inject a standalone PlantUML
preprocessor directive by embedding a newline in the ``title`` line."""

from __future__ import annotations

from src.application.modeling.artifact_write import format_diagram_puml


def _format(name: str) -> str:
    return format_diagram_puml(
        artifact_id="ARC@1.abc",
        diagram_type="archimate",
        name=name,
        puml_body="@startuml\nAlice -> Bob\n@enduml\n",
        keywords=None,
        version="0.1.0",
        status="active",
        last_updated="2026-07-22",
    )


def test_newline_in_name_cannot_inject_a_directive_line() -> None:
    out = _format("Innocent\n!include /etc/passwd")
    # No line may be a standalone !include the attacker controls.
    offending = [ln for ln in out.splitlines() if ln.strip().lower().startswith("!include /etc")]
    assert offending == []
    # The name is preserved as single-line title text (newline collapsed to a space).
    assert any(ln.startswith("title ") and "Innocent" in ln and "/etc/passwd" in ln for ln in out.splitlines())


def test_crlf_in_name_is_collapsed() -> None:
    out = _format("A\r\n%getenv(\"SECRET\")")
    assert not any(ln.strip().startswith("%getenv") for ln in out.splitlines())
