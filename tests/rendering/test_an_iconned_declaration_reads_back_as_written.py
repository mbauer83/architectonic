"""The ArchiMate declaration writer and the declaration reader agree once a label opens with an icon.

A label opens with a picture — the type's glyph or, since 0.11.0, an embedded icon — and the reader
must tell the picture from the name. Stated over what the writer permits: every picture form, with and
without a specialization line, a colour and a stereotype, relabelled and re-pictured in place.
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from pathlib import Path

import pytest

from src.application.puml_alias_declarations import (
    alias_declared_on,
    label_declared_on,
    picture_declared_on,
    relabelled_declaration,
    with_label_picture,
)
from src.application.puml_icon_header import icon_reference
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.app_bootstrap import get_module_registry
from src.infrastructure.rendering.archimate_entity_declarations import entity_declaration, entity_nest_declaration

ICON = icon_reference("ARCH_ICON_0123456789ab", "0.156")
GLYPH = "<$archimate_technology_node{scale=1.2}>"


def _node(name: str = "Cluster West") -> EntityRecord:
    return EntityRecord(
        artifact_id="NOD@1.aaaa.x", artifact_type="technology-node", name=name, version="0.1.0", status="draft",
        domain="technology", subdomain="", path=Path("x.md"), keywords=(), extra={}, content_text="",
        display_blocks={}, display_label="", display_alias="NOD_1_aaaa",
    )


CASES = list(itertools.product((None, ICON), (entity_declaration, entity_nest_declaration), (None, "West Europe")))


@pytest.mark.parametrize(("icon", "writer", "instance_label"), CASES)
def test_the_reader_reads_the_name_and_the_picture_the_writer_wrote(icon, writer, instance_label) -> None:
    line = writer(_node(), "N1", get_module_registry(), frozenset(), instance_label=instance_label, instance_icon=icon)

    assert alias_declared_on(line) is not None and alias_declared_on(line).alias == "N1"
    assert label_declared_on(line) == (instance_label or "Cluster West")
    assert picture_declared_on(line) == (icon or GLYPH)


@pytest.mark.parametrize(("icon", "writer", "instance_label"), CASES)
def test_a_relabel_keeps_the_picture_and_a_new_picture_keeps_the_name(icon, writer, instance_label) -> None:
    line = writer(_node(), "N1", get_module_registry(), frozenset(), instance_label=instance_label, instance_icon=icon)

    relabelled = relabelled_declaration(line, "Renamed")
    repictured = with_label_picture(line, GLYPH if icon else ICON)

    assert (label_declared_on(relabelled), picture_declared_on(relabelled)) == ("Renamed", icon or GLYPH)
    assert (label_declared_on(repictured), picture_declared_on(repictured)) == (
        instance_label or "Cluster West", GLYPH if icon else ICON
    )
    assert repictured.endswith(line[line.index('" ') :])  # stereotype, alias, colour and block untouched


def test_removing_the_picture_leaves_the_name() -> None:
    line = entity_declaration(_node(), "N1", get_module_registry(), frozenset(), instance_icon=ICON)

    bare = with_label_picture(line, "")

    assert picture_declared_on(bare) == "" and label_declared_on(bare) == "Cluster West"


def test_a_name_that_merely_contains_markup_is_still_a_name() -> None:
    entity = replace(_node(), name="Uses <img:x> literally")
    line = entity_declaration(entity, "N1", get_module_registry(), frozenset())

    assert label_declared_on(line) == "Uses <img:x> literally"
