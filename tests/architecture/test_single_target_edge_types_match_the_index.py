"""The edge types W048 checks are exactly the ones the renderer indexes single-target.

Two lists that must agree, and only one of them is executable. `_build_single_target` is a dict
comprehension keyed by `source`, so a second edge of that type out of one step is discarded when the
index is built; `SINGLE_TARGET_BY_SOURCE` is the list of types that happens to. If the renderer ever
switches one of them to `_build_multi_target` — which is what B45's loop work may need for
`step-flow` — the diagnostic would go on reporting a collision that no longer loses anything, and a
reader would be told to remove an edge the picture is perfectly able to draw.

The same shape as `test_fts_weights_match_their_columns`, and for the same reason: that gate caught a
missing weight on the first change after it was written. A list stating a fact about code the reader
cannot see from where the list lives needs the code to be asked.

Read from the source rather than by calling the renderer, because what is being checked is *which
builder each type is passed to* — a property of the call, not of any result.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.diagram_types.activity._step_graph import (
    SINGLE_TARGET_BY_SOURCE,
    SINGLE_TARGET_BY_TARGET,
)

_RENDERER = Path(__file__).resolve().parents[2] / "src" / "diagram_types" / "activity" / "renderer.py"


def _types_passed_to(builder: str) -> set[str]:
    """The connection-type literals handed to *builder* anywhere in the renderer."""
    tree = ast.parse(_RENDERER.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != builder:
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.add(argument.value)
    return found


def test_every_single_target_type_is_one_the_renderer_indexes_that_way() -> None:
    """A type listed but indexed many-target would have the diagnostic tell an author to remove an
    edge the drawing can carry perfectly well."""
    listed = set(SINGLE_TARGET_BY_SOURCE)
    indexed = _types_passed_to("_build_single_target")

    assert listed - indexed == set(), (
        f"these are checked for collisions but the renderer no longer indexes them single-target, so "
        f"the diagnostic would report a loss that does not happen: {sorted(listed - indexed)}"
    )


def test_every_type_indexed_single_target_is_checked() -> None:
    """The direction that loses edges silently: a type indexed single-target and not listed drops its
    second edge with nothing reporting it, which is the defect W048 exists for."""
    listed = set(SINGLE_TARGET_BY_SOURCE)
    indexed = _types_passed_to("_build_single_target")

    assert indexed - listed == set(), (
        f"the renderer indexes these single-target, so a second edge of one out of one step is "
        f"discarded before any walk runs — and nothing reports it: {sorted(indexed - listed)}"
    )


def test_the_multi_target_builder_is_still_the_exception() -> None:
    """`step-fork-branch` is named by its absence from the collision list, so the claim that it is the
    one safe type has to hold. If a second type joins it, its entry must leave the list above."""
    multi = _types_passed_to("_build_multi_target")

    assert multi == {"step-fork-branch"}
    assert multi.isdisjoint(SINGLE_TARGET_BY_SOURCE)


def test_the_note_index_keys_on_the_target() -> None:
    """The opposite key, and the reason the two lists are separate. `_build_notes_index` takes no
    connection-type argument — it names `step-note-of` inline — so this is read from the source it is
    written in rather than from a call."""
    source = _RENDERER.read_text(encoding="utf-8")
    index = source.index("def _build_notes_index")
    body = source[index : source.index("\ndef ", index + 1)]

    for conn_type in SINGLE_TARGET_BY_TARGET:
        assert conn_type in body, f"{conn_type} is checked as target-keyed but the note index does not read it"
    assert 'str(kc["target"])' in body, "the note index no longer keys on the target; the collision key moved"
