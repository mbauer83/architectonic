from __future__ import annotations

from src.infrastructure.gui.routers._diagram_context import (
    parse_explicit_connection_pairs as _parse_explicit_connection_pairs,
)


def test_parse_explicit_connection_pairs_supports_archimate_relation_macros() -> None:
    puml = """\
@startuml test
rectangle "A" as A
rectangle "B" as B
rectangle "C" as C
Rel_Influence_Down(A, B, "")
Rel_Association(B, C, "")
@enduml
"""

    pairs = _parse_explicit_connection_pairs(puml)

    assert ("A", "B") in pairs
    assert ("B", "C") in pairs


def test_parse_explicit_connection_pairs_handles_multiplicity_labels() -> None:
    """Multiplicity labels in macro calls must not affect connection pair extraction."""
    puml = """\
@startuml test
rectangle "A" as A
rectangle "B" as B
rectangle "C" as C
Rel_Realization_Up(A, B, "[1 -> 0..*]")
Rel_Association(B, C, "[1 ->]")
@enduml
"""

    pairs = _parse_explicit_connection_pairs(puml)

    assert ("A", "B") in pairs
    assert ("B", "C") in pairs


def test_parse_explicit_connection_pairs_stereotype_free_label() -> None:
    puml = """\
@startuml test
rectangle "A" as A
rectangle "B" as B
A --> B : HTTPS 443
@enduml
"""

    pairs = _parse_explicit_connection_pairs(puml)

    assert ("A", "B") in pairs


def test_parse_explicit_connection_pairs_no_label() -> None:
    puml = """\
@startuml test
rectangle "A" as A
rectangle "B" as B
A --> B
@enduml
"""

    pairs = _parse_explicit_connection_pairs(puml)

    assert ("A", "B") in pairs


def test_parse_explicit_connection_pairs_stereotype_same_as_bare_label() -> None:
    puml = """\
@startuml test
rectangle "A" as A
rectangle "B" as B
rectangle "C" as C
rectangle "D" as D
rectangle "E" as E
rectangle "F" as F
A --> B : <<serving>> HTTPS 443
C --> D : HTTPS 443
E --> F
@enduml
"""

    pairs = _parse_explicit_connection_pairs(puml)

    assert ("A", "B") in pairs
    assert ("C", "D") in pairs
    assert ("E", "F") in pairs
