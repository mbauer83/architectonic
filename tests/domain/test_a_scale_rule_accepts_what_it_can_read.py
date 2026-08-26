"""A scale rule is accepted exactly where the mode can read the attribute.

Two sets sit side by side in `viewpoint_criteria`: `NUMERIC_ATTRIBUTE_TYPES` and
`ORDERED_ATTRIBUTE_TYPES = NUMERIC_ATTRIBUTE_TYPES | {ORDINAL_KIND}`. The comparators use the wider
one — "an ordinal orders by its declared rank" — and the style-rule validator had picked the narrower,
so an ordinal scale attribute was refused at save time with *"scale attributes must be numeric or date
values"*. The ontology declares the rank, the comparators honour it, and the styling could not be
authored to use it. Six live attribute paths declare `x-scale: ordinal`.

And the guard read `declared not in (None, "reserved") and declared not in NUMERIC_ATTRIBUTE_TYPES`,
so a **reserved** path short-circuited the type check entirely. No reserved path is numeric or
date-typed — `id`, `name`, `type`, `specialization`, `group`, `domain`, `subdomain`, `status`,
`version` are all strings — so `mode: scale` on `status` was accepted and then styled nothing, on both
projection paths. After the artifact-local path learned to report rule outcomes, that silence became
an `expected-empty`: "nothing matched", for what is really "this mode cannot read this path".

A reserved path's type is known, so the check can be *made* rather than skipped. Refusing at save time
puts it where the author can act on it, and keeps the outcome vocabulary at the five members it has.
"""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_style_rule_validation import validate_style_rule
from src.domain.viewpoints.viewpoints import StyleRule

_LIKELIHOOD = ("rare", "unlikely", "possible", "likely", "almost-certain")


def _registries(**attribute_types: str) -> RegistrySnapshot:
    return RegistrySnapshot(
        known_entity_types=frozenset({"application-component"}),
        known_connection_types=frozenset(),
        known_specialization_slugs=frozenset(),
        entity_attribute_types=dict(attribute_types),
        connection_attribute_types={},
        entity_attribute_enums={"likelihood": _LIKELIHOOD},
    )


def _issues(attribute: str, registries: RegistrySnapshot) -> list[str]:
    rule = StyleRule(
        capability="node_color",
        mode="scale",
        scale_attribute=attribute,
        scale_tokens=("heat-low", "heat-high"),
    )
    found = validate_style_rule(
        rule,
        path="/presentation/styling_rules/0",
        representation_capabilities=frozenset({"node_color"}),
        registries=registries,
        check_ergonomics=False,
    )
    return [issue.code for issue in found]


class TestWhatTheModeCanRead:
    def test_an_integer_attribute_is_accepted(self) -> None:
        assert _issues("investment_level", _registries(investment_level="integer")) == []

    def test_a_number_attribute_is_accepted(self) -> None:
        assert _issues("cost", _registries(cost="number")) == []

    def test_a_date_attribute_is_accepted(self) -> None:
        assert _issues("reviewed_on", _registries(reviewed_on="date")) == []

    def test_an_ordinal_attribute_is_accepted(self) -> None:
        """The one that was refused. Its rank is declared, and the comparators already read it."""
        assert _issues("likelihood", _registries(likelihood="ordinal")) == []


class TestWhatTheModeCannotRead:
    def test_a_plain_string_attribute_is_refused(self) -> None:
        assert "operator-type-mismatch" in _issues("owner", _registries(owner="string"))

    def test_an_array_attribute_is_refused(self) -> None:
        assert "operator-type-mismatch" in _issues("licences", _registries(licences="array"))

    def test_an_unknown_attribute_is_refused_as_unknown(self) -> None:
        assert "unknown-attribute" in _issues("no_such_thing", _registries())

    def test_a_reserved_path_the_mode_cannot_read_is_refused(self) -> None:
        """`status` is a reserved path and a string. It used to be accepted and then style nothing —
        the guard skipped the type check for anything reserved."""
        assert "operator-type-mismatch" in _issues("status", _registries())

    def test_every_reserved_path_is_refused_rather_than_a_named_one(self) -> None:
        """Stated over the whole reserved vocabulary, not over the one that was found: none of them is
        numeric, date-typed or ordinal, so a scale rule can read none of them. A test naming `status`
        alone would pass while `domain` stayed accepted-and-inert."""
        from src.domain.viewpoints.viewpoint_criteria import RESERVED_ENTITY_PATHS

        for path in sorted(RESERVED_ENTITY_PATHS):
            assert "operator-type-mismatch" in _issues(path, _registries()), (
                f"a scale rule on the reserved path {path!r} is accepted and styles nothing"
            )
