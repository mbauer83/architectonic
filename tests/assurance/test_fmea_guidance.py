"""Failure-mode guidance: reachable, complete, and saying the things that must be said.

Three claims in this content are not decoration, and each is asserted rather than trusted to
survive editing.

*It is not additional coverage.* A failure-mode analysis cannot find a control or coordination flaw
where nothing failed — most of what a control-structure analysis exists for. Guidance that framed it
as extra coverage would invite the conclusion that a completed matrix means the system is analysed.

*A priority never overrides a constraint.* The pressure to price away an obligation arrives as a
plausible argument, so the text has to refuse it in advance.

*The detection axis runs the other way from conventional FMEA.* An expert who thinks the tool is
wrong about that stops trusting the derived values too.
"""

from __future__ import annotations

import pytest

from src.application.assurance_guidance import lookup
from src.application.assurance_guidance_failure_modes import FAILURE_MODE_GUIDANCE

_TOPICS = ("fmea-failure-modes", "fmea-effects", "fmea-causes", "fmea-controls", "fmea-factors")


class TestEveryTopicIsReachableAndComplete:
    def test_the_five_topics_exist(self) -> None:
        assert set(FAILURE_MODE_GUIDANCE) == set(_TOPICS)

    @pytest.mark.parametrize("topic", _TOPICS)
    def test_the_topic_resolves_through_the_shared_lookup(self, topic: str) -> None:
        """Merged into the same lookup as the other methods, so one call site serves all of them."""
        assert lookup(topic)["topic"] == topic

    @pytest.mark.parametrize("topic", _TOPICS)
    def test_the_topic_carries_the_full_shape(self, topic: str) -> None:
        entry = lookup(topic)

        for field in ("step", "what", "why", "how", "standards"):
            assert str(entry.get(field) or "").strip(), f"{topic} has no {field}"

    @pytest.mark.parametrize("topic", _TOPICS)
    def test_the_topic_cites_the_published_standards(self, topic: str) -> None:
        standards = lookup(topic)["standards"]

        assert isinstance(standards, list)
        joined = " ".join(standards)
        assert "J1739" in joined and "AIAG-VDA" in joined and "60812" in joined


class TestTheFramingIsCarriedNotAssumed:
    def test_it_is_never_presented_as_coverage_additional_to_the_control_analysis(self) -> None:
        why = str(lookup("fmea-failure-modes")["why"])

        assert "never as extra coverage" in why
        assert "cannot find a coordination flaw" in why

    def test_the_priority_is_stated_never_to_override_a_constraint(self) -> None:
        entry = lookup("fmea-factors")

        text = str(entry["priority_never_overrides_a_constraint"])
        assert "never close, weaken, defer" in text
        assert "no affordance" in text

    def test_the_absence_of_a_risk_priority_number_is_explained(self) -> None:
        """Stated so its absence reads as a decision rather than as something missing."""
        text = str(lookup("fmea-factors")["if_you_already_know_fmea"])

        assert "no risk priority number" in text
        assert "ordinals" in text

    def test_the_detectability_direction_is_stated(self) -> None:
        text = str(lookup("fmea-factors")["if_you_already_know_fmea"])

        assert "higher means MORE detectable" in text

    def test_occurrence_is_explained_as_asserted_rather_than_derivable(self) -> None:
        why = str(lookup("fmea-factors")["why"])

        assert "nothing in the model measures a failure rate" in why
        assert "look computed" in why

    def test_targeting_signals_are_stated_not_to_be_factors(self) -> None:
        text = str(lookup("fmea-factors")["targeting_signals_are_not_factors"])

        assert "never composed into a score" in text

    def test_telemetry_is_stated_not_to_raise_detectability(self) -> None:
        why = str(lookup("fmea-controls")["why"])

        assert "never raises the band" in why

    def test_a_dismissal_is_stated_to_count_as_coverage(self) -> None:
        how = str(lookup("fmea-failure-modes")["how"])

        assert "counts as coverage" in how


class TestTheGuidanceCarriesNoPlanningReferences:
    @pytest.mark.parametrize("topic", _TOPICS)
    def test_no_topic_cites_this_project_s_own_planning_documents(self, topic: str) -> None:
        """Standards references are citations of published work; a decision id or work-unit id
        would be an internal artefact leaking into content a user reads."""
        import re

        text = " ".join(str(v) for v in lookup(topic).values())

        assert not re.search(r"\bWU-[A-Z]?\d", text)
        assert not re.search(r"\bD\d{1,2}\b", text)
        assert "the plan" not in text.lower()
