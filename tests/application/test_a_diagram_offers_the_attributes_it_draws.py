"""What a reader can be offered for one diagram: the types on it, and their attributes.

The panel behind "colour by" and "print with the entity". Its shape is decided by three facts about
the domain, each of which a simpler answer gets wrong:

**A specialization is its own row.** Two entities of one type carrying different specializations do not
offer the same attributes, because a specialization contributes its own. Grouping by type alone would
offer each of them the other's attributes and then fail to read them.

**A ramp needs an order and a palette needs a bounded set**, and the ontology says which is which. A
number, a date and an *ordinal* have an order — the last because `x-scale: ordinal` declares it — while
an enum and a boolean have a bounded set with no inherent order. Free text and lists have neither, and
saying so is better than offering a colour that means nothing.

**Presence is read where values live.** This repository records attribute values in a Properties table
in the document body and declares only their types in frontmatter, so a check of `extra` reports every
value absent. That mistake was made once in this release already, which is why the panel asks
`read_attribute_value` — the same function the styling asks, so the panel cannot offer an attribute the
styling then fails to read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.viewpoints.diagram_attribute_panel import offers_for_diagram
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.specializations import SpecializationCatalog

_SCHEMATA = ".arch-repo/schemata"


def _entity(
    n: int,
    *,
    artifact_type: str = "application-component",
    specializations: tuple[str, ...] = (),
    **attributes: object,
) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"APP@{n}",
        artifact_type=artifact_type,
        name=f"component {n}",
        version="0.1.0",
        status="active",
        domain="application",
        subdomain="",
        path=Path("e.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=f"component {n}",
        display_alias=f"APP{n}",
        specializations=specializations,
        attributes=dict(attributes),
    )


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """A repository whose one type declares one attribute of each interesting kind."""
    root = tmp_path / "repo"
    schemata = root / _SCHEMATA
    schemata.mkdir(parents=True)
    (schemata / "attributes.application-component.schema.json").write_text(
        json.dumps({
            "type": "object",
            "properties": {
                "risk_score": {"type": "integer"},
                "reviewed_on": {"type": "string", "format": "date"},
                "severity": {"type": "string", "enum": ["minor", "moderate", "major"], "x-scale": "ordinal"},
                "lifecycle": {"type": "string", "enum": ["planned", "active", "retired"]},
                "is_external": {"type": "boolean"},
                "owner": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        }),
        encoding="utf-8",
    )
    return root


def _offers(entities: list[EntityRecord], repo_root: Path):
    return offers_for_diagram(
        entities,
        repo_root,
        specialization_catalog=SpecializationCatalog(),
        profile_registry=ProfileRegistry.empty(),
    )


def _by_name(offer) -> dict:  # noqa: ANN001
    return {attribute.name: attribute for attribute in offer.attributes}


class TestWhichColourAnAttributeCanTake:
    def test_a_number_takes_a_ramp(self, repo_root: Path) -> None:
        attributes = _by_name(_offers([_entity(1)], repo_root)[0])

        assert attributes["risk_score"].colour == "ramp"

    def test_a_date_takes_a_ramp(self, repo_root: Path) -> None:
        attributes = _by_name(_offers([_entity(1)], repo_root)[0])

        assert attributes["reviewed_on"].colour == "ramp"

    def test_an_ordinal_takes_a_ramp_and_reports_its_declared_order(self, repo_root: Path) -> None:
        """The order is the model's, not alphabetical. `moderate` sits between the other two only
        because the enum is written in ascending rank, which is what `x-scale: ordinal` asserts."""
        attributes = _by_name(_offers([_entity(1)], repo_root)[0])

        assert attributes["severity"].colour == "ramp"
        assert attributes["severity"].declared_type == "ordinal"
        assert attributes["severity"].values == ("minor", "moderate", "major")

    def test_an_unordered_enum_takes_a_palette(self, repo_root: Path) -> None:
        attributes = _by_name(_offers([_entity(1)], repo_root)[0])

        assert attributes["lifecycle"].colour == "palette"
        assert attributes["lifecycle"].declared_type == "string"

    def test_a_boolean_takes_a_palette_of_two(self, repo_root: Path) -> None:
        attributes = _by_name(_offers([_entity(1)], repo_root)[0])

        assert attributes["is_external"].colour == "palette"
        assert attributes["is_external"].values == ("false", "true")

    def test_free_text_and_lists_take_no_colour(self, repo_root: Path) -> None:
        """Offering one would be a ramp over prose or one colour per entity."""
        attributes = _by_name(_offers([_entity(1)], repo_root)[0])

        assert attributes["owner"].colour == "none"
        assert attributes["tags"].colour == "none"

    def test_every_attribute_is_printable_whatever_its_colour(self, repo_root: Path) -> None:
        """A reader may want an owner's name on the picture as readily as a risk score."""
        attributes = _by_name(_offers([_entity(1)], repo_root)[0])

        assert all(attribute.printable for attribute in attributes.values())


class TestWhatIsActuallyThere:
    def test_an_attribute_a_drawn_entity_carries_is_counted(self, repo_root: Path) -> None:
        entities = [_entity(1, risk_score=3), _entity(2, risk_score=7), _entity(3)]

        attributes = _by_name(_offers(entities, repo_root)[0])

        assert attributes["risk_score"].present_on == 2

    def test_an_attribute_nothing_carries_is_listed_with_a_count_of_zero(self, repo_root: Path) -> None:
        """Listed, not hidden. A dropped row says "this type has no such attribute", which is false —
        and a reader who cannot see the attribute cannot know why nothing is coloured."""
        attributes = _by_name(_offers([_entity(1, risk_score=3)], repo_root)[0])

        assert "owner" in attributes
        assert attributes["owner"].present_on == 0

    def test_presence_is_read_from_the_properties_table_not_frontmatter(self, repo_root: Path) -> None:
        """The mistake this release already made once: `extra` holds declared types, `attributes` holds
        the values, and a check of the former reports everything absent."""
        entity = _entity(1, risk_score=4)
        assert entity.extra == {}, "the fixture puts the value where the product puts it"

        attributes = _by_name(_offers([entity], repo_root)[0])

        assert attributes["risk_score"].present_on == 1

    def test_the_count_is_per_type_rather_than_per_diagram(self, repo_root: Path) -> None:
        entities = [_entity(1, risk_score=3), _entity(2, artifact_type="data-object")]

        offers = {offer.entity_type: offer for offer in _offers(entities, repo_root)}

        assert offers["application-component"].drawn == 1
        assert offers["data-object"].drawn == 1


class TestASpecializationIsItsOwnRow:
    def test_a_type_and_its_specialization_are_separate_rows(self, repo_root: Path) -> None:
        entities = [_entity(1), _entity(2, specializations=("module",))]

        rows = {(offer.entity_type, offer.specialization) for offer in _offers(entities, repo_root)}

        assert rows == {("application-component", ""), ("application-component", "module")}

    def test_an_entity_carrying_two_specializations_appears_under_each(self, repo_root: Path) -> None:
        """ArchiMate §15.2 permits several, and each contributes its own attributes — so a reader
        looking at one of them must find it, not only the first."""
        entities = [_entity(1, specializations=("module", "gateway"))]

        rows = {offer.specialization for offer in _offers(entities, repo_root)}

        assert rows == {"module", "gateway"}


class TestTheAnswerIsStable:
    def test_rows_and_attributes_come_back_in_a_fixed_order(self, repo_root: Path) -> None:
        """A panel whose rows move between requests is a panel a reader cannot learn."""
        entities = [_entity(2, artifact_type="data-object"), _entity(1)]

        first = _offers(entities, repo_root)
        second = _offers(list(reversed(entities)), repo_root)

        assert [(o.entity_type, o.specialization) for o in first] == [
            (o.entity_type, o.specialization) for o in second
        ]
        assert [a.name for a in first[0].attributes] == [a.name for a in second[0].attributes]

    def test_a_type_with_no_declared_attributes_is_still_a_row(self, repo_root: Path) -> None:
        """It says "this type is here and offers nothing", which is what folds to a stated line rather
        than to an empty drawer."""
        offers = {offer.entity_type: offer for offer in _offers([_entity(1, artifact_type="data-object")], repo_root)}

        assert offers["data-object"].attributes == ()
        assert offers["data-object"].drawn == 1
