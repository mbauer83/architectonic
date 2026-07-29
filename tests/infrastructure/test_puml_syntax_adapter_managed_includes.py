"""The PlantUML syntax adapter must not report generated include fragments as broken.

`_archimate-glyphs.puml`, `_archimate-stereotypes.puml` and `_archimate-relations.puml` are
written by `generate_static_includes` at `arch-init`. They carry sprite, stereotype and
relation definitions for other diagrams to `!include`, and have no `@startuml` of their
own — PlantUML run against one standalone exits 100, which the syntax checker reports as
`E350`.

The whole-repository pass never meets them: the inventory scans `diagram-catalog/diagrams/`
and they live one level above, in `diagram-catalog/`. But `artifact_verify_file` verifies a
caller-supplied path, so an agent given a repository listing can point it at one and be
told a correct, generated file is malformed — a false error against a file the user cannot
fix by hand, since editing it is explicitly forbidden by its own header.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.rendering.puml_safety import is_managed_include
from src.infrastructure.verification.adapters import DefaultPumlSyntaxAdapter

_MANAGED = ("_archimate-glyphs.puml", "_archimate-stereotypes.puml",
            "_archimate-relations.puml", "_macros.puml")


@pytest.mark.parametrize("basename", _MANAGED)
def test_generated_fragments_are_recognised_as_managed(basename: str) -> None:
    assert is_managed_include(basename)


@pytest.mark.parametrize("basename", ["diagram.puml", "_not-managed.puml", "archimate-glyphs.puml"])
def test_ordinary_diagrams_are_not(basename: str) -> None:
    assert not is_managed_include(basename)


@pytest.mark.parametrize("basename", _MANAGED)
def test_check_one_reports_nothing_for_a_fragment(tmp_path: Path, basename: str) -> None:
    """No subprocess, no findings — a fragment is not a diagram to be checked."""
    fragment = tmp_path / basename
    fragment.write_text("sprite $x <svg/>\n")  # no @startuml, as generated
    assert DefaultPumlSyntaxAdapter().check_one(fragment, str(fragment)) == []


def test_check_batch_answers_for_every_path_it_was_given(tmp_path: Path) -> None:
    """A batch mixing fragments with real diagrams must still return one entry per input.
    Dropping the fragments from the returned mapping would make a caller that iterates the
    result silently skip diagrams, or raise on a missing key."""
    fragment = tmp_path / "_archimate-glyphs.puml"
    fragment.write_text("sprite $x <svg/>\n")
    diagram = tmp_path / "real.puml"
    diagram.write_text("@startuml\nAlice -> Bob\n@enduml\n")

    out = DefaultPumlSyntaxAdapter().check_batch([fragment, diagram])

    assert set(out) == {fragment, diagram}
    assert out[fragment] == []


def test_a_batch_of_only_fragments_runs_no_check_at_all(tmp_path: Path) -> None:
    fragment = tmp_path / "_archimate-stereotypes.puml"
    fragment.write_text("skinparam x y\n")
    assert DefaultPumlSyntaxAdapter().check_batch([fragment]) == {fragment: []}
