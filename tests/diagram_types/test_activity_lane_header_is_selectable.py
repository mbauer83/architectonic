"""A swimlane header carries the lane's identity, as every other labelled construct does.

A lane may be bound — `allowed_bindings.entity.swimlane` permits `represents` and `traces-to` — and
the binding persisted, but the renderer wrote a bare `|Label|`. So an action, a decision and a
partition were all clickable and the lane alone was not, in the same module. That asymmetry is what
made it read as an oversight rather than a decision.

**The notation permits it, which had to be established before writing anything.** The renderer records
the negative precedent for forks — `fork [[url]]` is a syntax error, which is why a fork is not
selectable and why a lane might have been the same. Measured on the pinned PlantUML 1.2026.3: a
two-lane body whose first header reads `|[[arch://ln_ops Operations]]|` renders one anchor with
`xlink:href="arch://ln_ops"`, and both headers still show their own text. So a lane is not a fork.

One header emission, not two. `renderer.py` wrote the first lane's header and `_emission.py` wrote
every switch after it, in the same spelling — so wiring one and not the other would have made the
first lane the only unclickable one, which is a worse bug than the one being fixed.
"""

from __future__ import annotations

import pytest

from src.diagram_types.activity._step_links import lane_header, sentinel_of


class TestTheHeaderCarriesTheLane:
    def test_a_bound_lane_carries_its_entity(self) -> None:
        header = lane_header({"id": "ln_ops", "label": "Operations", "entity_id": "ROL@1.a.engineer"})

        assert sentinel_of(header) == "ROL@1.a.engineer"

    def test_an_unbound_lane_carries_its_own_id(self) -> None:
        """The same fallback `sentinel_target` gives every other kind: a lane with no binding is
        still a thing the viewer can resolve to, and treating it differently would put a second
        rule beside the one the module already states."""
        header = lane_header({"id": "ln_ops", "label": "Operations"})

        assert sentinel_of(header) == "ln_ops"

    def test_the_label_is_still_the_visible_text(self) -> None:
        header = lane_header({"id": "ln_ops", "label": "Operations"})

        assert "Operations" in header

    def test_it_is_still_a_lane_header(self) -> None:
        header = lane_header({"id": "ln_ops", "label": "Operations"})

        assert header.startswith("|") and header.endswith("|")


class TestWhatTheLabelMayContain:
    def test_a_pipe_in_the_label_cannot_close_the_header(self) -> None:
        """`|` delimits a lane header, so a label carrying one would end it early and leave the
        rest as body text. `puml_text` already replaces it; this pins that it is applied here."""
        header = lane_header({"id": "ln", "label": "Ops | Eng"})

        assert header.count("|") == 2

    def test_a_bracket_in_the_label_does_not_close_the_link(self) -> None:
        header = lane_header({"id": "ln", "label": "Ops [draft]"})

        assert sentinel_of(header) == "ln"

    def test_a_bracket_in_the_id_round_trips(self) -> None:
        assert sentinel_of(lane_header({"id": "odd]id", "label": "Ops"})) == "odd]id"

    def test_a_lane_with_no_label_falls_back_to_its_id(self) -> None:
        header = lane_header({"id": "ln_ops"})

        assert "ln_ops" in header


class TestBothEmissionPointsUseIt:
    """The duplication that made this a two-place fix. Asserted over the source, because the defect
    was that two modules spelled one line and only one of them would have been changed."""

    @pytest.mark.parametrize(
        "module",
        ["src/diagram_types/activity/renderer.py", "src/diagram_types/activity/_emission.py"],
    )
    def test_neither_module_spells_a_lane_header_itself(self, module: str) -> None:
        from pathlib import Path

        source = Path(module).read_text(encoding="utf-8")

        assert 'f"|{' not in source, f"{module} still builds a lane header of its own"
        assert "lane_header(" in source, f"{module} does not call the one emission"
