"""Which relationship types reach an authoring client, and with what.

A relationship type is as answerable as an element type: it carries its own
``create_when``/``never_create_when``, populated from the imported guidance overlay. It appears in
the payload when it has something to say — guidance, specializations, or a metadata schema — and is
omitted otherwise, so the response stays compact without hiding an answerable relationship.

The connection types here are fixture-owned, so exact assertions are safe.
"""

from __future__ import annotations

from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo
from src.infrastructure.write.artifact_write._connection_metadata_guidance import connection_type_guidance


def _info(name: str, *, create_when: str = "", never_create_when: str = "") -> ConnectionTypeInfo:
    return ConnectionTypeInfo(
        artifact_type=name,
        conn_lang="archimate",
        create_when=create_when,
        never_create_when=never_create_when,
    )


def _catalog(*entries: SpecializationInfo) -> SpecializationCatalog:
    return SpecializationCatalog(entries=tuple(entries))


def _specialization(parent_type: str, slug: str) -> SpecializationInfo:
    return SpecializationInfo(
        module_alias="archimate-4",
        concept_kind="connection",
        parent_type=parent_type,
        slug=slug,
        name=slug.replace("-", " ").title(),
    )


class TestInclusion:
    def test_type_with_guidance_is_included(self) -> None:
        entries = connection_type_guidance(
            SpecializationCatalog.empty(),
            connection_types={"archimate-serving": _info("archimate-serving", create_when="cw")},
        )
        assert [entry["name"] for entry in entries] == ["archimate-serving"]
        assert entries[0]["create_when"] == "cw"
        assert entries[0]["never_create_when"] == ""

    def test_type_with_only_never_create_when_is_included(self) -> None:
        entries = connection_type_guidance(
            SpecializationCatalog.empty(),
            connection_types={"archimate-flow": _info("archimate-flow", never_create_when="nw")},
        )
        assert [entry["name"] for entry in entries] == ["archimate-flow"]

    def test_type_with_neither_guidance_nor_specializations_is_omitted(self) -> None:
        entries = connection_type_guidance(
            SpecializationCatalog.empty(),
            connection_types={"archimate-association": _info("archimate-association")},
        )
        assert entries == []

    def test_type_with_specializations_but_no_guidance_is_still_included(self) -> None:
        entries = connection_type_guidance(
            _catalog(_specialization("archimate-assignment", "behavior-assignment")),
            connection_types={"archimate-assignment": _info("archimate-assignment")},
        )
        assert [entry["name"] for entry in entries] == ["archimate-assignment"]
        specializations = entries[0]["specializations"]
        assert isinstance(specializations, list)
        assert [spec["slug"] for spec in specializations] == ["behavior-assignment"]

    def test_entries_are_ordered_by_type_name(self) -> None:
        entries = connection_type_guidance(
            SpecializationCatalog.empty(),
            connection_types={
                "archimate-serving": _info("archimate-serving", create_when="cw"),
                "archimate-access": _info("archimate-access", create_when="cw"),
            },
        )
        assert [entry["name"] for entry in entries] == ["archimate-access", "archimate-serving"]
