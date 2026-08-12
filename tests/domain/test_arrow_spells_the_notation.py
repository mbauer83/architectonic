"""A connection type's PUML arrow draws the end markers its notation declares.

`notation` is the authority on how a relationship is drawn — structural, renderer-agnostic, and
already honoured by the graph canvas, which draws both containment diamonds. `puml_arrow` is the
PlantUML spelling of the same fact, maintained by hand beside it, and the two drifted: composition
and aggregation both declared a diamond at the source and both spelled `-->`, so the graph view
showed an ArchiMate diamond and the diagram showed an anonymous arrow for the same relation. With
`show_stereotype: false` on both, nothing on the picture said which relation it was.

The claim that put them there is in `relation_notation`'s own docstring — "PlantUML expresses
containment by nesting rather than by a diamond, so composition and aggregation are both spelled
`-->` there". The first half is true and is why nesting stays the default; the second does not
follow, and PlantUML disproves it: `A o-- B` between two rectangles renders a hollow diamond at A
(`<polygon fill="none" points="91,78.6 87,84.6 91,90.6 95,84.6 …"/>`) and `*--` a filled one.
Nesting remains how containment is drawn whenever it CAN be nested; the arrow is what a containment
falls back to — a second parent, a cycle, a member claimed by an authored group — and there the
diamond is what says which relation it is.

**Scope: the end markers PlantUML can spell.** Not every notation has an arrow form. A `ball` at
the source (assignment) has none, so `-->` is the honest approximation and is not asserted here.
Line style is not asserted either, and two types disagree on it today — `archimate-access`
declares a dotted line and spells a solid `-->`, and `flow`/`influence` declare dashed and spell
the dotted `..>`. Those are real and recorded as their own item rather than folded in here, where
they would change relations this change has no argument about.
"""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.infrastructure.app_bootstrap import get_module_registry

#: The source-end markers PlantUML has a spelling for, and what that spelling is.
_SOURCE_MARKER_TOKEN = {"filled-diamond": "*", "hollow-diamond": "o"}


def _connection_types() -> list[tuple[str, ConnectionTypeInfo]]:
    return sorted((str(name), info) for name, info in get_module_registry().all_connection_types().items())


def _diamond_types() -> list[tuple[str, ConnectionTypeInfo]]:
    return [
        (name, info) for name, info in _connection_types() if info.notation.source in _SOURCE_MARKER_TOKEN
    ]


class TestADeclaredDiamondIsSpelled:
    def test_some_type_declares_a_diamond(self) -> None:
        """Guards the assertions below against a catalogue that stopped declaring any."""
        assert _diamond_types(), "no connection type declares a diamond — the walk found nothing to check"

    @pytest.mark.parametrize("name,info", _diamond_types(), ids=lambda value: value if isinstance(value, str) else "")
    def test_the_arrow_opens_with_the_declared_marker(self, name: str, info: ConnectionTypeInfo) -> None:
        expected = _SOURCE_MARKER_TOKEN[info.notation.source]

        assert info.puml_arrow.startswith(expected), (
            f"{name} declares notation.source={info.notation.source!r} but spells "
            f"puml_arrow={info.puml_arrow!r}, which draws no diamond — the graph canvas and the "
            "diagram then disagree about what the relation is"
        )


class TestNoTypeDrawsAMarkerItDoesNotDeclare:
    """The other direction, so the arrow cannot grow a diamond the notation does not claim."""

    @pytest.mark.parametrize(
        "name,info", _connection_types(), ids=lambda value: value if isinstance(value, str) else ""
    )
    def test_an_arrow_marker_is_declared_in_the_notation(self, name: str, info: ConnectionTypeInfo) -> None:
        for marker, token in _SOURCE_MARKER_TOKEN.items():
            if info.puml_arrow.startswith(token):
                assert info.notation.source == marker, (
                    f"{name} spells puml_arrow={info.puml_arrow!r} but declares "
                    f"notation.source={info.notation.source!r}"
                )
