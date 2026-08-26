"""A guard the author writes is a guard the reader sees.

The pair, not each side: the generator emits the grouping line, PlantUML draws it, and the test
reads the guard back out of the rendered SVG. Nothing between the two could be asserted usefully on
its own, because the source was *well-formed* — `alt [features computed]` is valid PlantUML. It is
valid and it means something else: a single `[...]` is PlantUML's link syntax, `[target label]`, so
the guard rendered as a hyperlink whose target was the first token and whose label was the rest.
The word "features" was simply absent from the image, and `artifact_verify` had nothing to object to.

**Stated over multi-word guards on purpose.** A single-word guard round-trips through the broken
emission — `alt [computed]` draws `computed` — and single-word guards are the common case, which is
why this shipped. A fixture of one-word guards passes against the defect.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.diagram_types.sequence.renderer import SequencePumlRenderer
from src.infrastructure.rendering.puml_runtime import render_puml_svg

_REPO = Path(__file__).resolve().parents[2] / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"

#: Guards a person would actually write. The single-token one is here to prove the walk covers the
#: case that already worked, so a regression cannot hide behind it.
_GUARDS = ("features computed", "timeout or unknown error", "a b c d", "computed")


def _diagram_entities(first_guard: str, second_guard: str) -> dict[str, object]:
    return {
        "lifeline": [{"id": "l1", "label": "Caller"}, {"id": "l2", "label": "Service"}],
        "message": [
            {"id": "m1", "label": "request", "kind": "synchronous"},
            {"id": "m2", "label": "reply", "kind": "reply"},
        ],
        "grouping": [{
            "id": "g1",
            "kind": "alt",
            "operands": [
                {"guard": first_guard, "start_message_id": "m1", "end_message_id": "m1"},
                {"guard": second_guard, "start_message_id": "m2", "end_message_id": "m2"},
            ],
        }],
        "_connections": [
            {"conn_type": "seq-from", "source": "m1", "target": "l1"},
            {"conn_type": "seq-to", "source": "m1", "target": "l2"},
            {"conn_type": "seq-from", "source": "m2", "target": "l2"},
            {"conn_type": "seq-to", "source": "m2", "target": "l1"},
        ],
    }


def _rendered_text(body: str) -> list[str]:
    svg, errors = render_puml_svg(body, _REPO)
    assert svg, f"render produced nothing: {errors}"
    return [re.sub(r"\s+", " ", t).strip() for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg)]


def _body_for(first_guard: str, second_guard: str) -> str:
    return SequencePumlRenderer({}).render_body(
        "guard round trip", [], [], "sequence", _REPO,
        diagram_entities=_diagram_entities(first_guard, second_guard),
    )


class TestAGuardSurvivesIntoTheImage:
    @pytest.mark.parametrize("guard", _GUARDS)
    def test_every_word_of_an_alt_guard_is_drawn(self, guard: str) -> None:
        drawn = " ".join(_rendered_text(_body_for(guard, "otherwise")))

        for word in guard.split():
            assert word in drawn, f"{word!r} of guard {guard!r} is missing from the image: {drawn!r}"

    @pytest.mark.parametrize("guard", _GUARDS)
    def test_every_word_of_an_else_guard_is_drawn(self, guard: str) -> None:
        """The `else` branch emits through its own line and had the same brackets."""
        drawn = " ".join(_rendered_text(_body_for("first", guard)))

        for word in guard.split():
            assert word in drawn, f"{word!r} of guard {guard!r} is missing from the image: {drawn!r}"


class TestTheGeneratorDoesNotWriteTheBracketsPlantumlAdds:
    @pytest.mark.parametrize("guard", _GUARDS)
    def test_no_grouping_line_wraps_its_guard_in_brackets(self, guard: str) -> None:
        """The emission rule itself, so a failure names the cause rather than a missing word."""
        for line in _body_for(guard, guard).splitlines():
            if line.startswith(("alt ", "else ", "opt ", "loop ", "break ", "critical ")):
                assert "[" not in line, f"{line!r} writes brackets PlantUML supplies itself"
