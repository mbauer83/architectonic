"""A scratchpad records what its notes reference, and the index can be asked in reverse.

**The references live on the pad, not on its notes**, and that is not a convenience. A note stops being
a searchable record once it holds a `model_ref` — the model then has an artifact standing for the same
thought, and returning both offers two answers for one thing. But a bound note is *precisely* the one
that references something, so reading the references off the note records would find none of them. The
pad is also what a reader navigates to.

The reverse map is maintained the way `diagrams_by_reference` is, including on the incremental path: a
pad is re-indexed in-session when it is saved, so a map built only at scan time would go on linking a
pad that no longer mentions the entity.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.scratchpad.indexing import parse_scratchpad


def _pad_document(*notes: str) -> str:
    body = "\n".join(notes)
    return f"""\
artifact-id: SCR@1780000000.aaaaaa.thinking
artifact-type: scratchpad
name: Thinking
description: a pad
version: 0.1.0
status: active
meta-ontology: archimate-4
notes:
{body}
"""


def _note(note_id: str, title: str, *, ref: str | None = None) -> str:
    """A note, bound to model content or not.

    A bound note carries `element-type` because the aggregate requires it: a reference without a type
    describes content the scratchpad cannot say anything about, so `invariants.py` refuses it.
    """
    lines = [f"- id: {note_id}", f"  title: {title}"]
    if ref is not None:
        lines += [
            "  destination: element",
            "  element-type: application-component",
            "  model-ref:",
            f"    artifact-id: {ref}",
            "    kind: bound",
        ]
    return "\n".join(lines)


@pytest.fixture()
def pad_file(tmp_path: Path):
    def write(*notes: str) -> Path:
        path = tmp_path / "pad.scratchpad.yaml"
        path.write_text(_pad_document(*notes), encoding="utf-8")
        return path
    return write


class TestWhatTheParseKeeps:
    def test_a_bound_note_s_reference_reaches_the_pad(self, pad_file) -> None:  # noqa: ANN001
        pad, _notes = parse_scratchpad(pad_file(_note("n1", "A thought", ref="APP@1.x.alpha")), group="g")

        assert pad is not None
        assert pad.references == frozenset({"APP@1.x.alpha"})

    def test_the_bound_note_is_not_a_searchable_record(self, pad_file) -> None:  # noqa: ANN001
        """Which is exactly why the reference has to travel on the pad: the note carrying it is gone
        from the records, so nothing downstream could read it off one."""
        pad, notes = parse_scratchpad(pad_file(_note("n1", "A thought", ref="APP@1.x.alpha")), group="g")

        assert pad is not None
        assert notes == []
        assert pad.references

    def test_an_unbound_note_contributes_no_reference(self, pad_file) -> None:  # noqa: ANN001
        pad, notes = parse_scratchpad(pad_file(_note("n1", "Still thinking")), group="g")

        assert pad is not None
        assert pad.references == frozenset()
        assert [n.title for n in notes] == ["Still thinking"]

    def test_every_bound_note_contributes(self, pad_file) -> None:  # noqa: ANN001
        pad, _notes = parse_scratchpad(
            pad_file(
                _note("n1", "One", ref="APP@1.x.alpha"),
                _note("n2", "Two", ref="APP@2.x.beta"),
                _note("n3", "Three"),
            ),
            group="g",
        )

        assert pad is not None
        assert pad.references == frozenset({"APP@1.x.alpha", "APP@2.x.beta"})

    def test_a_pad_binding_one_artifact_twice_is_not_indexed_at_all(self, pad_file) -> None:  # noqa: ANN001
        """Not a set-versus-list question: the aggregate refuses it outright. Two notes bound to one
        entity would render the same element twice and lift as one, so `invariants.py` rejects the
        document and the parse answers with the silence a malformed pad has always got — the product's
        verifier is where a broken file is reported, not the index."""
        pad, notes = parse_scratchpad(
            pad_file(_note("n1", "One", ref="APP@1.x.alpha"), _note("n2", "Two", ref="APP@1.x.alpha")),
            group="g",
        )

        assert (pad, notes) == (None, [])
