"""strip_startuml_name removes the whole title after @startuml.

Regression guard: the previous `@startuml\\s+\\S+` form stripped only the first word, so a
multi-word diagram name left "@startuml <rest>" behind. PlantUML then named the output file
by the leftover words and the temp→final rename missed it — a misnamed file and a silently
failed render.
"""

from __future__ import annotations

from src.infrastructure.rendering.puml_safety import strip_startuml_name


def test_strips_multi_word_name() -> None:
    body = "@startuml Artifact Persistence Model\nclass A\n@enduml\n"
    assert strip_startuml_name(body).splitlines()[0] == "@startuml"


def test_strips_single_word_name() -> None:
    assert strip_startuml_name("@startuml Foo\nclass A\n").splitlines()[0] == "@startuml"


def test_noop_without_name() -> None:
    body = "@startuml\nclass A\n@enduml\n"
    assert strip_startuml_name(body) == body


def test_only_first_startuml_affected() -> None:
    # Defensive: a second @startuml token in the body (rare) is left untouched.
    body = "@startuml One Two\nnote: @startuml Three Four\n@enduml\n"
    out = strip_startuml_name(body)
    assert out.splitlines()[0] == "@startuml"
    assert "@startuml Three Four" in out
