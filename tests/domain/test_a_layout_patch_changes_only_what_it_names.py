"""A layout patch sets and removes the entries it names, and refuses, whole, one whose base moved."""

from __future__ import annotations

import pytest

from src.domain.diagrams.layout.layout_block import Layout, MalformedLayout, layout_as_written, read_layout
from src.domain.diagrams.layout.layout_patch import LayoutConflict, patched, read_layout_patch

A = "APP@1712870400.xVrBYD"
B = "APP@1712870401.aaaaaa"


def _layout() -> Layout:
    return read_layout({"elements": {A: {"x": 1, "y": 2}, B: {"x": 3, "y": 4}}, "z": {A: 1}})


def test_set_and_remove_leave_every_other_entry_as_it_was() -> None:
    patch = read_layout_patch({"elements": {A: {"value": {"x": 5, "y": 6, "w": 10, "h": 12}}, B: None}})

    assert layout_as_written(patched(_layout(), patch)) == {
        "elements": {A: {"x": 5, "y": 6, "w": 10, "h": 12}},
        "z": {A: 1},
    }


def test_an_entry_read_as_what_it_still_is_applies() -> None:
    patch = read_layout_patch({"elements": {A: {"value": {"x": 9, "y": 9}, "based_on": {"x": 1, "y": 2}}}})

    assert layout_as_written(patched(_layout(), patch))["elements"] == {
        A: {"x": 9, "y": 9}, B: {"x": 3, "y": 4},
    }


def test_an_entry_whose_base_moved_refuses_the_whole_patch() -> None:
    patch = read_layout_patch({
        "elements": {A: {"value": {"x": 9, "y": 9}, "based_on": {"x": 0, "y": 0}}, B: None},
    })

    with pytest.raises(LayoutConflict) as refused:
        patched(_layout(), patch)
    assert refused.value.entries == (("elements", A),)


def test_an_entry_read_as_absent_conflicts_with_one_that_is_there() -> None:
    patch = read_layout_patch({"z": {B: {"value": 2, "based_on": None}, A: {"value": 3, "based_on": None}}})

    with pytest.raises(LayoutConflict) as refused:
        patched(_layout(), patch)
    assert refused.value.entries == (("z", A),)


@pytest.mark.parametrize(
    "raw",
    [{"elements": {A: {"x": 1, "y": 2}}}, {"shapes": {}}, {"elements": {A: {"value": {"x": 1}}}}, []],
)
def test_what_is_not_a_patch_is_refused_with_a_sentence(raw: object) -> None:
    with pytest.raises(MalformedLayout):
        read_layout_patch(raw)
