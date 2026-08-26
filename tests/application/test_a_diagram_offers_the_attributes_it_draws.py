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

**An attribute several types share reads across the diagram.** Colouring is by attribute name and
applies to every drawn entity that has one, so an attribute more than one drawn type declares
*identically* is a global reading and is offered as one. Identically is the load-bearing word: two
types declaring `status` as unrelated enums are not sharing an attribute, and a global colouring keyed
on the name alone would put two meanings on one scale.

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


def _schema_for(repo_root: Path, entity_type: str, properties: dict) -> Path:
    """Declare an attribute schema for a second type, so agreement between rows can be stated."""
    path = repo_root / _SCHEMATA / f"attributes.{entity_type}.schema.json"
    path.write_text(json.dumps({"type": "object", "properties": properties}), encoding="utf-8")
    return path


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


def _panel(entities: list[EntityRecord], repo_root: Path):
    return offers_for_diagram(
        entities,
        repo_root,
        specialization_catalog=SpecializationCatalog(),
        profile_registry=ProfileRegistry.empty(),
    )


def _offers(entities: list[EntityRecord], repo_root: Path):
    """Just the per-type rows, which is what most of these tests are about."""
    return _panel(entities, repo_root).types


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

    def test_an_attribute_a_colour_cannot_read_is_still_offered(self, repo_root: Path) -> None:
        """Every attribute can be printed beside its entity — a reader may want an owner's name on the
        picture as readily as a risk score — so there is no `printable` flag to assert. What this
        asserts instead is that saying "no colour" does not withdraw the row: `owner` and `tags` are
        offered with `colour == "none"` rather than left out, which is the only way a reader learns
        they can print what they cannot colour."""
        offered = _by_name(_offers([_entity(1)], repo_root)[0])

        assert not hasattr(next(iter(offered.values())), "printable"), (
            "a flag that is always true is not information; the offer carries no such field"
        )
        assert {"owner", "tags"} <= set(offered)


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
        _schema_for(repo_root, "data-object", {"risk_score": {"type": "integer"}})
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

    def test_a_type_with_no_declared_attributes_is_not_a_row(self, repo_root: Path) -> None:
        """This is a panel for choosing, and a row with nothing to choose is a fold that opens on
        nothing. It was kept at first on the reasoning that "this type is here and offers nothing" is
        information — it is, but not information this panel is for, and the entity list beside it
        already says which types are drawn."""
        offers = {offer.entity_type for offer in _offers([_entity(1, artifact_type="data-object")], repo_root)}

        assert offers == set()


def _shared_by_name(panel) -> dict:  # noqa: ANN001
    return {offer.attribute.name: offer for offer in panel.shared}


class TestWhatReadsAcrossTheDiagram:
    """The shared section. Its own class because its rules are about *agreement between* rows, where
    everything above is about one row."""

    def test_an_attribute_two_types_declare_identically_is_shared(self, repo_root: Path) -> None:
        second = _schema_for(repo_root, "data-object", {"risk_score": {"type": "integer"}})
        assert second.exists()
        entities = [_entity(1, risk_score=3), _entity(2, artifact_type="data-object", risk_score=9)]

        panel = _panel(entities, repo_root)

        shared = _shared_by_name(panel)
        assert "risk_score" in shared
        assert shared["risk_score"].on_rows == ("application-component", "data-object")

    def test_a_shared_attribute_counts_entities_across_the_whole_diagram(self, repo_root: Path) -> None:
        """Not the sum of the per-row counts. An entity carrying two specializations appears under each
        of them, and adding those rows up would count it twice."""
        _schema_for(repo_root, "data-object", {"risk_score": {"type": "integer"}})
        entities = [
            _entity(1, specializations=("module", "gateway"), risk_score=3),
            _entity(2, artifact_type="data-object", risk_score=9),
        ]

        panel = _panel(entities, repo_root)

        assert _shared_by_name(panel)["risk_score"].attribute.present_on == 2

    def test_an_attribute_only_one_type_declares_is_not_shared(self, repo_root: Path) -> None:
        panel = _panel([_entity(1, risk_score=3)], repo_root)

        assert panel.shared == ()

    def test_the_same_name_declared_differently_is_disputed_rather_than_shared(
        self, repo_root: Path
    ) -> None:
        """The whole point of "identically". `risk_score` as an integer on one type and a string on
        another is two attributes with one name, and a global ramp over both would put two meanings on
        one scale. Reported, because leaving it silently out of `shared` makes it look like a name
        nothing else declares."""
        _schema_for(repo_root, "data-object", {"risk_score": {"type": "string"}})
        entities = [_entity(1, risk_score=3), _entity(2, artifact_type="data-object", risk_score="high")]

        panel = _panel(entities, repo_root)

        assert panel.shared == ()
        assert panel.disputed == ("risk_score",)

    def test_two_enums_with_different_members_are_disputed(self, repo_root: Path) -> None:
        """Same declared type and same colour kind, different value sets — so a member's colour would
        mean one thing on one type and nothing on the other."""
        _schema_for(
            repo_root, "data-object", {"lifecycle": {"type": "string", "enum": ["draft", "final"]}}
        )
        entities = [_entity(1), _entity(2, artifact_type="data-object")]

        panel = _panel(entities, repo_root)

        assert "lifecycle" in panel.disputed
        assert "lifecycle" not in _shared_by_name(panel)

    def test_a_shared_attribute_still_appears_under_each_type(self, repo_root: Path) -> None:
        """The shared row is a shortcut to the same choice, not a move: the type fold is where the
        per-type presence count lives, and a reader who went looking under `data-object` must find it."""
        _schema_for(repo_root, "data-object", {"risk_score": {"type": "integer"}})
        entities = [_entity(1, risk_score=3), _entity(2, artifact_type="data-object")]

        panel = _panel(entities, repo_root)

        per_type = {offer.entity_type: [a.name for a in offer.attributes] for offer in panel.types}
        assert "risk_score" in per_type["data-object"]
        assert "risk_score" in per_type["application-component"]

    def test_a_specialization_row_counts_as_a_second_declarer(self, repo_root: Path) -> None:
        """A specialization is its own row, so an attribute the bare type and a specialization both
        offer reads across two rows — which is what a global colouring will actually cover."""
        entities = [_entity(1, risk_score=3), _entity(2, specializations=("module",), risk_score=4)]

        panel = _panel(entities, repo_root)

        assert _shared_by_name(panel)["risk_score"].on_rows == (
            "application-component",
            "application-component/module",
        )
