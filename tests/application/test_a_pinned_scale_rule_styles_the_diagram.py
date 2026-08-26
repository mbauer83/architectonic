"""A style rule pinned to a diagram works, and says so when it does not.

Measured on the served repository before this existed:
`GET /api/diagrams/ARC@1784488894.WwyJAa.resource-investment-map/viewpoint-projection` answered
`applied: true` with sixteen items, **every one `"style": {}`**, and `scale_legends`, `rule_outcomes`
and `warnings` all empty. That diagram pins `resource-map@3`, whose presentation declares one
`node_color` rule with `mode: scale`, `scale_attribute: investment_level` and explicit bounds 1–5 — and
four of the resources it draws *do* carry that attribute, in the Properties table of their document
bodies. So the diagram had every input it needed and coloured nothing.

Two defects, and they are separate:

**A whole style mode is inert on this path.** `project_artifact_local` never called
`calculate_scale_bounds` and passed no `scale_bounds`, and `_scale_value` returns `None` for any rule
index absent from the bounds map. So a scale rule styled nothing here *even when it declared explicit
bounds* — which is why the shipped catalogue happening to declare them did not save it, and why this
file states the contract over what the mode **permits** rather than over the one shape in use.

**The "no silent no-op" contract did not hold on this path.** `classify_style_rule_outcomes` exists,
is documented as that contract, and was called only from the repository projection. So a rule that
styled nothing on a diagram was unreportable: no `unresolvable`, no `expected-empty`, no warning. The
same viewpoint gave two different answers depending on how it was reached, which is the shape of
defect this project has paid for repeatedly.

**And the one attribute kind with a declared rank could not be ramped at all.** The ontology declares
`x-scale: ordinal` — six live paths — with `ordinal_rank` to read it and comparators that already
order by it. `_number` handled numbers, dates and their string forms and nothing else, and the *style
rule validator* refused an ordinal scale attribute outright, so it could not even be authored. Two
sets sat side by side: `NUMERIC_ATTRIBUTE_TYPES` and `ORDERED_ATTRIBUTE_TYPES`, the latter already
containing the ordinal, and the newer feature had picked the narrower one.

Fixture-owned throughout. The corpus exercises one rule of one mode with one bounds shape, so a test
that read the repository would assert almost none of what follows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.viewpoints.artifact_projection import project_artifact_local
from src.domain.concept_scope import ConceptScope
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoints import (
    PresentationSpec,
    StyleRule,
    ViewpointApplication,
    ViewpointDefinition,
)

_LIKELIHOOD = ("rare", "unlikely", "possible", "likely", "almost-certain")


def _entity(n: int, **extra: object) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"APP@{n}",
        artifact_type="application-component",
        name=f"component {n}",
        version="0.1.0",
        status="active",
        domain="application",
        subdomain="",
        path=Path("e.md"),
        keywords=(),
        extra=dict(extra),
        content_text="",
        display_blocks={},
        display_label=f"component {n}",
        display_alias=f"APP{n}",
    )


class _Access:
    """The read access the projection needs, over a fixture population."""

    def __init__(self, entities: list[EntityRecord]) -> None:
        self._entities = {e.artifact_id: e for e in entities}

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_connection(self, artifact_id: str):  # noqa: ANN001, ANN201, ARG002
        return None


def _registries(**attribute_types: str) -> RegistrySnapshot:
    return RegistrySnapshot(
        known_entity_types=frozenset({"application-component"}),
        known_connection_types=frozenset(),
        known_specialization_slugs=frozenset(),
        entity_attribute_types=dict(attribute_types),
        connection_attribute_types={},
        entity_attribute_enums={"likelihood": _LIKELIHOOD} if "likelihood" in attribute_types else {},
    )


def _definition(rule: StyleRule) -> ViewpointDefinition:
    return ViewpointDefinition(
        slug="fixture",
        version=1,
        name="Fixture",
        presentation=PresentationSpec(representation="diagram", styling_rules=(rule,)),
    )


def _project(rule: StyleRule, entities: list[EntityRecord], registries: RegistrySnapshot):
    return project_artifact_local(
        _definition(rule),
        ViewpointApplication(viewpoint_slug="fixture", pinned_version=1, target_kind="diagram", target_id="ARC@1"),
        diagram_scope=ConceptScope.unrestricted(),
        entity_type_infos={},
        placed_entities=entities,
        placed_connections=[],
        enforcement="warn",
        read_access=_Access(entities),
        registries=registries,
    )


def _scale(attribute: str, minimum: object = None, maximum: object = None) -> StyleRule:
    return StyleRule(
        capability="node_color",
        mode="scale",
        scale_attribute=attribute,
        scale_min=minimum,  # type: ignore[arg-type]
        scale_max=maximum,  # type: ignore[arg-type]
        scale_tokens=("heat-low", "heat-high"),
    )


def _styles(projection) -> dict[str, dict]:  # noqa: ANN001
    return {item.item_id: dict(item.style) for item in projection.items}


class TestTheModeWorksAtAll:
    def test_explicit_bounds_style_the_drawn_entities(self) -> None:
        entities = [_entity(1, investment_level=1), _entity(2, investment_level=5)]

        projection = _project(_scale("investment_level", 1, 5), entities, _registries(investment_level="integer"))

        styles = _styles(projection)
        assert styles["APP@1"]["node_color"].position == pytest.approx(0.0)
        assert styles["APP@2"]["node_color"].position == pytest.approx(1.0)

    def test_data_driven_bounds_come_from_what_is_drawn(self) -> None:
        """Both bounds `None` — the shape the shipped catalogue never uses, and the one that makes a
        colouring usable with no configuration at all."""
        entities = [_entity(1, investment_level=10), _entity(2, investment_level=20)]

        projection = _project(_scale("investment_level"), entities, _registries(investment_level="integer"))

        styles = _styles(projection)
        assert styles["APP@1"]["node_color"].position == pytest.approx(0.0)
        assert styles["APP@2"]["node_color"].position == pytest.approx(1.0)

    def test_one_explicit_bound_and_one_drawn(self) -> None:
        entities = [_entity(1, investment_level=5), _entity(2, investment_level=15)]

        projection = _project(_scale("investment_level", 0, None), entities, _registries(investment_level="integer"))

        styles = _styles(projection)
        assert styles["APP@1"]["node_color"].position == pytest.approx(5 / 15)

    def test_a_legend_is_reported_with_the_bounds_it_used(self) -> None:
        entities = [_entity(1, investment_level=2)]

        projection = _project(_scale("investment_level", 1, 5), entities, _registries(investment_level="integer"))

        assert len(projection.scale_legends) == 1
        legend = projection.scale_legends[0]
        assert (legend.capability, legend.attribute) == ("node_color", "investment_level")
        assert (legend.minimum, legend.maximum) == (1.0, 5.0)
        assert legend.tokens == ("heat-low", "heat-high")


class TestAbsentIsNotZero:
    def test_an_entity_without_the_attribute_is_unstyled(self) -> None:
        """Absent and zero are different facts, and a ramp that conflates them lies about the model."""
        entities = [_entity(1, investment_level=3), _entity(2)]

        projection = _project(_scale("investment_level", 1, 5), entities, _registries(investment_level="integer"))

        styles = _styles(projection)
        assert "node_color" in styles["APP@1"]
        assert styles["APP@2"] == {}

    def test_a_zero_value_is_styled_at_the_low_end(self) -> None:
        entities = [_entity(1, investment_level=0)]

        projection = _project(_scale("investment_level", 0, 5), entities, _registries(investment_level="integer"))

        assert _styles(projection)["APP@1"]["node_color"].position == pytest.approx(0.0)


class TestDegenerateBounds:
    def test_equal_bounds_give_the_low_end_and_do_not_divide_by_zero(self) -> None:
        entities = [_entity(1, investment_level=7), _entity(2, investment_level=7)]

        projection = _project(_scale("investment_level"), entities, _registries(investment_level="integer"))

        for style in _styles(projection).values():
            assert style["node_color"].position == pytest.approx(0.0)


class TestAnOrdinalRampsByItsDeclaredRank:
    def test_an_ordinal_attribute_is_positioned_by_rank(self) -> None:
        """The ontology declares the order; the ramp reads it rather than inventing one.

        `likelihood` is `rare → unlikely → possible → likely → almost-certain`, so `possible` sits at
        the middle of a five-member scale. Alphabetical ordering would put it fourth, which is what
        treating an ordinal as a plain string does — and is why `registry_snapshot` resolves an
        ordinal to its own kind in preference to its JSON-Schema type.
        """
        entities = [
            _entity(1, likelihood="rare"),
            _entity(2, likelihood="possible"),
            _entity(3, likelihood="almost-certain"),
        ]

        projection = _project(_scale("likelihood"), entities, _registries(likelihood="ordinal"))

        styles = _styles(projection)
        assert styles["APP@1"]["node_color"].position == pytest.approx(0.0)
        assert styles["APP@2"]["node_color"].position == pytest.approx(0.5)
        assert styles["APP@3"]["node_color"].position == pytest.approx(1.0)

    def test_an_ordinals_bounds_are_its_declared_range_not_the_drawn_extremes(self) -> None:
        """The enum *is* the scale. A diagram where everything is mild must not paint it as severe.

        Only `unlikely` and `possible` are drawn — ranks 1 and 2 of 0..4. Drawn-extreme bounds would
        place them at 0.0 and 1.0, saying "least and most likely" about two values the model calls
        neither.
        """
        entities = [_entity(1, likelihood="unlikely"), _entity(2, likelihood="possible")]

        projection = _project(_scale("likelihood"), entities, _registries(likelihood="ordinal"))

        styles = _styles(projection)
        assert styles["APP@1"]["node_color"].position == pytest.approx(0.25)
        assert styles["APP@2"]["node_color"].position == pytest.approx(0.5)

    def test_a_value_outside_the_declared_scale_is_unstyled_not_ranked_lowest(self) -> None:
        """`ordinal_rank` answers `None` for an unrecognised member, "because a rank of zero reads as
        the lowest member and would flatter unrecognised data into looking benign"."""
        entities = [_entity(1, likelihood="catastrophic"), _entity(2, likelihood="likely")]

        projection = _project(_scale("likelihood"), entities, _registries(likelihood="ordinal"))

        styles = _styles(projection)
        assert styles["APP@1"] == {}
        assert "node_color" in styles["APP@2"]

    def test_the_legend_names_the_members_rather_than_their_ranks(self) -> None:
        """A legend reading `0 → 4` reports how the ramp is computed, not what it shows.

        The rank is how a position is found; the member name is the scale the model declared. A
        reader given the numbers has to know that `likelihood` has five members and that they are
        written in ascending order — which is exactly the knowledge a legend exists to supply.
        """
        entities = [_entity(1, likelihood="rare"), _entity(2, likelihood="almost-certain")]

        projection = _project(_scale("likelihood"), entities, _registries(likelihood="ordinal"))

        legend = projection.scale_legends[0]
        assert (legend.minimum_label, legend.maximum_label) == ("rare", "almost-certain")

    def test_a_numeric_legend_has_no_labels_because_its_numbers_are_the_answer(self) -> None:
        entities = [_entity(1, investment_level=2)]

        projection = _project(_scale("investment_level", 1, 5), entities, _registries(investment_level="integer"))

        legend = projection.scale_legends[0]
        assert (legend.minimum_label, legend.maximum_label) == (None, None)

    def test_explicit_bounds_may_name_members(self) -> None:
        """`scale_min: "unlikely"` — authored bounds go through the same rank lookup, or an ordinal
        rule with explicit bounds silently degrades to drawn extremes, which is the exact failure the
        declared-range rule exists to prevent."""
        entities = [_entity(1, likelihood="unlikely"), _entity(2, likelihood="likely")]

        projection = _project(
            _scale("likelihood", "unlikely", "likely"), entities, _registries(likelihood="ordinal")
        )

        styles = _styles(projection)
        assert styles["APP@1"]["node_color"].position == pytest.approx(0.0)
        assert styles["APP@2"]["node_color"].position == pytest.approx(1.0)


class TestNoSilentNoOp:
    def test_every_authored_rule_has_exactly_one_outcome(self) -> None:
        entities = [_entity(1, investment_level=3)]

        projection = _project(_scale("investment_level", 1, 5), entities, _registries(investment_level="integer"))

        assert len(projection.rule_outcomes) == 1
        assert projection.rule_outcomes[0].rule_index == 0

    def test_a_rule_that_styled_something_reports_applied(self) -> None:
        entities = [_entity(1, investment_level=3)]

        projection = _project(_scale("investment_level", 1, 5), entities, _registries(investment_level="integer"))

        assert projection.rule_outcomes[0].kind == "applied"
        assert projection.rule_outcomes[0].applied_count == 1

    def test_a_rule_whose_data_is_absent_reports_expected_empty(self) -> None:
        """The measured case: the attribute is declared and nothing carries it. That is a legitimate
        state, and saying so is the difference between it and a broken rule."""
        entities = [_entity(1), _entity(2)]

        projection = _project(_scale("investment_level", 1, 5), entities, _registries(investment_level="integer"))

        assert projection.rule_outcomes[0].kind == "expected-empty"
        assert projection.rule_outcomes[0].matched_count == 0

    def test_a_rule_naming_an_unknown_attribute_reports_unresolvable(self) -> None:
        entities = [_entity(1)]

        projection = _project(_scale("no_such_attribute", 1, 5), entities, _registries())

        assert projection.rule_outcomes[0].kind == "unresolvable"
        assert projection.warnings, "an unresolvable rule styles nothing and must say so"


class TestTheOtherModesAreUnchanged:
    """Established before the edit, not after. `match` and `range` have never been exercised on this
    path by shipped content — the corpus pins exactly one viewpoint carrying exactly one rule, and it
    is a `scale` — so "unchanged" is a fixture claim and is stated as one."""

    def test_a_match_rule_styles_what_its_criteria_select(self) -> None:
        from src.domain.viewpoints.viewpoint_criteria import (
            AttributeCondition,
            EntityCriteriaGroup,
            ValueRef,
        )

        rule = StyleRule(
            capability="node_color",
            mode="match",
            match_criteria=EntityCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="status", comparator="eq", value=ValueRef(literal="active")
                    ),
                ),
            ),
            value="critical",
        )
        entities = [_entity(1)]

        projection = _project(rule, entities, _registries())

        assert _styles(projection)["APP@1"]["node_color"] == "critical"

    def test_a_range_rule_bands_a_numeric_attribute(self) -> None:
        from src.domain.viewpoints.viewpoints import RangeBand

        rule = StyleRule(
            capability="node_color",
            mode="range",
            range_attribute="investment_level",
            range_bands=(
                RangeBand(minimum=None, maximum=3, value="positive"),
                RangeBand(minimum=3, maximum=None, value="critical"),
            ),
        )
        entities = [_entity(1, investment_level=1), _entity(2, investment_level=4)]

        projection = _project(rule, entities, _registries(investment_level="integer"))

        styles = _styles(projection)
        assert styles["APP@1"]["node_color"] == "positive"
        assert styles["APP@2"]["node_color"] == "critical"
