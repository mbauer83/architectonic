"""A kind table that contradicts itself is refused, in a sentence that names the rows and the fix.

Every case starts from the shipped rows and breaks one thing, so each refusal is shown to come from
that one thing and from nothing else in the table.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.domain.repository.artifact_kind_consistency import kind_table_contradictions
from src.domain.repository.artifact_location import ARTIFACT_KINDS, KindDeclaration, artifact_kind


def _with(*changed: KindDeclaration) -> tuple[KindDeclaration, ...]:
    """The shipped table with *changed* rows standing in for the rows of the same name."""
    by_name = {row.name: row for row in changed}
    return tuple(by_name.get(row.name, row) for row in ARTIFACT_KINDS)


def _only(messages: list[str]) -> str:
    assert len(messages) == 1, messages
    return messages[0]


def test_two_rows_under_one_name() -> None:
    table = (*ARTIFACT_KINDS, replace(artifact_kind("icon"), roots=(("elsewhere",),), id_prefix=None))

    message = _only(kind_table_contradictions(table))

    assert "2 rows are named 'icon'" in message and "rename all but one" in message


def test_two_rows_claiming_one_suffix_under_one_root() -> None:
    table = _with(replace(artifact_kind("icon"), roots=artifact_kind("document").roots))

    message = _only(kind_table_contradictions(table))

    assert "'document' and 'icon' both claim a file ending '.md' under 'docs'" in message
    assert "give one of them a suffix or a root the other does not have" in message


def test_two_rows_claiming_one_path_through_a_root_inside_the_other_s() -> None:
    """`docs/` and `docs/notes/` are two roots and one place for a file to be."""
    table = _with(replace(artifact_kind("icon"), roots=(("docs", "notes"),)))

    message = _only(kind_table_contradictions(table))

    assert "'document' and 'icon' both claim" in message and "'docs' and 'docs/notes'" in message


def test_a_root_for_every_project_overlaps_a_literal_one_beneath_projects() -> None:
    table = _with(replace(artifact_kind("document"), roots=(("projects", "core", "model"),)))

    message = _only(kind_table_contradictions(table))

    assert "'entity' and 'document' both claim a file ending '.md'" in message


def test_a_longer_suffix_under_a_shared_root_is_how_two_kinds_are_told_apart() -> None:
    """Not a contradiction: an entity and its outgoing file share both model roots."""
    assert artifact_kind("entity").roots == artifact_kind("connection").roots
    assert kind_table_contradictions(ARTIFACT_KINDS) == []


def test_two_rows_declaring_one_id_prefix() -> None:
    table = _with(replace(artifact_kind("scratchpad"), id_prefix="ICO"))

    message = _only(kind_table_contradictions(table))

    assert "'icon' and 'scratchpad' both declare the id prefix 'ICO'" in message
    assert "change one of them" in message


@pytest.mark.parametrize("prefix", ["ico", "I", "TOOLONGX", "IC0"])
def test_an_id_prefix_no_id_can_carry(prefix: str) -> None:
    message = _only(kind_table_contradictions(_with(replace(artifact_kind("icon"), id_prefix=prefix))))

    assert f"'icon' declares the id prefix {prefix!r}, which no id can carry" in message


def test_a_row_verified_with_the_model_that_does_not_move_its_generation() -> None:
    table = _with(replace(artifact_kind("diagram"), moves_model_generation=False))

    message = _only(kind_table_contradictions(table))

    assert "'diagram' is verified with the model and does not move the model generation" in message
    assert "`standalone` or `unverified`, or let it move the generation" in message


def test_a_row_with_nowhere_to_keep_its_files() -> None:
    message = _only(kind_table_contradictions(_with(replace(artifact_kind("icon"), roots=()))))

    assert "'icon' has no root directory" in message


@pytest.mark.parametrize("suffixes", [(), ("md",), (".",)])
def test_a_row_whose_suffixes_end_no_file_name(suffixes: tuple[str, ...]) -> None:
    message = _only(kind_table_contradictions(_with(replace(artifact_kind("icon"), suffixes=suffixes))))

    assert "'icon' declares suffixes" in message and "starts with a dot" in message


def test_a_public_list_of_names_the_rows_do_not_give() -> None:
    """A row added without its name in the `Literal` leaves every typed contract one kind short."""
    table = tuple(row for row in ARTIFACT_KINDS if row.name != "scratchpad")

    message = _only(kind_table_contradictions(table))

    assert "`ArtifactKindName` lists" in message and "'scratchpad'" in message


def test_a_verified_list_the_rows_do_not_give() -> None:
    table = _with(replace(artifact_kind("icon"), verification="unverified"))

    message = _only(kind_table_contradictions(table))

    assert "`VerifiedArtifactKindName` lists" in message
