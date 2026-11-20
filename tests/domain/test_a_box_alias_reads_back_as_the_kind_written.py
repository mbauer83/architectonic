"""The alias a renderer gives a computed box is read back as the kind of box it was written for.

A rendered picture keeps nothing of which box is which except this alias, so the three writers and
the one reader are held as a pair. Stated over what an alias may be built from — any domain name, any
canvas namespace, any count — not over the handful the shipped ontology produces today.
"""

from __future__ import annotations

import pytest

from src.domain.diagrams.layout.box_aliases import (
    BoxKind,
    authored_grouping_alias,
    box_kind,
    domain_box_alias,
    type_box_alias,
)

_NO_ELEMENTS: frozenset[str] = frozenset()


@pytest.mark.parametrize(
    "domain", ["business", "common", "implementation-migration", "a domain / with.marks", "", "GRPT"]
)
def test_a_domain_box_reads_back_as_a_domain_box(domain: str) -> None:
    alias = domain_box_alias(domain)

    assert box_kind(alias, element_aliases=_NO_ELEMENTS) is BoxKind.DOMAIN
    assert alias.replace("_", "").isalnum(), f"{alias!r} is not something PlantUML takes as an alias"


@pytest.mark.parametrize("namespace", ["", "business_", "DOM_", "GRPA_", "a_b_"])
@pytest.mark.parametrize("ordinal", [1, 12, 400])
def test_a_type_box_reads_back_as_a_type_box(namespace: str, ordinal: int) -> None:
    assert box_kind(type_box_alias(namespace, ordinal), element_aliases=_NO_ELEMENTS) is BoxKind.TYPE


@pytest.mark.parametrize("rank", [1, 7, 120])
def test_an_authored_grouping_reads_back_as_one(rank: int) -> None:
    assert box_kind(authored_grouping_alias(rank), element_aliases=_NO_ELEMENTS) is BoxKind.AUTHORED_GROUPING


def test_the_three_writers_never_produce_the_same_alias() -> None:
    """Two boxes of different kinds under one alias would be one box to PlantUML."""
    written = [
        domain_box_alias("business"), domain_box_alias("1"),
        type_box_alias("", 1), type_box_alias("business_", 1),
        authored_grouping_alias(1),
    ]
    assert len(set(written)) == len(written)


@pytest.mark.parametrize("alias", ["GRP_WRITE", "Team / Project A", "Front Office", "dom_lowercase"])
def test_a_box_somebody_wrote_by_hand_is_a_grouping_an_author_made(alias: str) -> None:
    assert box_kind(alias, element_aliases=_NO_ELEMENTS) is BoxKind.AUTHORED_GROUPING


@pytest.mark.parametrize("alias", ["PRC_abc123", "DOM_looks_computed", "GRPT_looks_computed", "GRPA_9"])
def test_an_alias_the_diagram_draws_an_instance_under_is_an_element(alias: str) -> None:
    """The diagram's own statement of what it holds outranks a spelling: an element may be called
    anything, and a box that is one must never be filed under a rule."""
    assert box_kind(alias, element_aliases={alias}) is BoxKind.ELEMENT
