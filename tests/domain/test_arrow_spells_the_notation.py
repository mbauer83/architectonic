"""A connection type's PUML arrow draws exactly the notation it declares.

`notation` is the authority on how a relationship is drawn — structural, renderer-agnostic, and
honoured by the graph canvas. `puml_arrow` is the PlantUML spelling of the same fact, and the two
drifted repeatedly because each was maintained by hand beside the other:

* composition and aggregation declared a diamond at the source and spelled `-->`, so the graph view
  showed an ArchiMate diamond and the diagram an anonymous arrow for the same relation. With
  `show_stereotype: false` on both, nothing on the picture said which relation it was.
* `archimate-access` declared a dotted line and spelled a solid `-->`; `flow` and `influence`
  declared dashed and spelled the dotted `..>`. Checked against the ArchiMate notation before
  either side was touched: access is dotted, flow and influence are dashed, so the declarations
  were right and the spellings were wrong.
* **Twelve further types agreed with nothing.** They declared no `notation` at all, which the
  parser answers with a plausible default — solid line, filled arrow — while their long-standing
  `puml_arrow` said dotted, or reversed, or a hollow triangle. "Not declared" and "declared as the
  default" were indistinguishable, so the graph canvas drew a dotted UML dependency as a solid
  arrow and no test could see it. Those were fixed the other way round: the arrow was the authored
  intent, so the notation now states what each has always drawn.

So the assertion is the derivation itself — `puml_arrow_for(notation)` — rather than a property of
one end. A weaker gate is what let each of these through in turn.

**Where PlantUML cannot spell a notation, the derivation is the closest legal token**, and it is
still derived: `archimate-assignment` declares a ball at the source, which PlantUML has no form
for, so it draws a plain line. The gate holds the token to the derivation, not to a promise that
PlantUML can express every notation.
"""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.domain.ontology_representation.relation_notation import puml_arrow_for
from src.infrastructure.app_bootstrap import build_module_registry

#: The **complete** vocabulary, not the runtime one. A parametrised walk is expanded at collection
#: time, and `get_module_registry()` drops a module whose optional capability is unavailable — so
#: with 20 xdist workers probing the confidential store concurrently, workers disagreed about
#: whether the assurance types exist and pytest refused the run for collecting different tests.
#: `generate_types.py` takes the same view for the same reason: "so the generated file is identical
#: on every machine — e.g. with or without the confidential assurance store configured".
_REGISTRY = build_module_registry(complete_vocabulary=True)


def _connection_types() -> list[tuple[str, ConnectionTypeInfo]]:
    return sorted((str(name), info) for name, info in _REGISTRY.all_connection_types().items())


class TestEveryArrowSpellsItsNotation:
    @pytest.mark.parametrize(
        "name,info", _connection_types(), ids=lambda value: value if isinstance(value, str) else ""
    )
    def test_the_arrow_is_the_one_the_notation_derives(self, name: str, info: ConnectionTypeInfo) -> None:
        expected = puml_arrow_for(info.notation)

        assert info.puml_arrow == expected, (
            f"{name} declares notation line={info.notation.line!r} source={info.notation.source!r} "
            f"target={info.notation.target!r}, which draws {expected!r}, but spells "
            f"puml_arrow={info.puml_arrow!r} — the graph canvas and the diagram then disagree "
            "about what the relation is"
        )


class TestTheWalkCoversWhatItClaimsTo:
    """Guards on the walk above: a catalogue that stopped declaring the interesting cases would
    leave every assertion vacuously true, which is how the first version of this gate passed
    against the defect it was written for."""

    def test_the_catalogue_is_not_empty(self) -> None:
        assert _connection_types()

    @pytest.mark.parametrize(
        "predicate,what",
        [
            (lambda info: info.notation.source in ("filled-diamond", "hollow-diamond"), "a diamond"),
            (lambda info: info.notation.line == "dashed", "a dashed line"),
            (lambda info: info.notation.line == "dotted", "a dotted line"),
            (lambda info: info.notation.target == "hollow-triangle", "a hollow triangle"),
        ],
    )
    def test_some_type_declares_it(self, predicate: object, what: str) -> None:
        assert any(predicate(info) for _, info in _connection_types()), (  # type: ignore[operator]
            f"no connection type declares {what} — the walk proves nothing about it"
        )
