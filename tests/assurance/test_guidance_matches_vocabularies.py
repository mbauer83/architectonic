"""Method guidance may not teach a vocabulary the software does not implement.

`assurance_guidance('stpa-ucas')` taught the Handbook's four guidewords while everything that
executes — the attribute enum, the UCA matrix columns, the wizard, the store migration — had moved to
the five in `domain.assurance.uca_guidewords`. An analyst following the guidance enumerates four
columns of a five-column matrix, and no check anywhere reports the fifth as unasked: the guidance is
the one surface whose errors are invisible to the software, because nothing downstream reads it.

So the binding is asserted here rather than assumed: the text is composed from the vocabulary, and
these fail if either the composition or the vocabulary changes without the other.
"""

from __future__ import annotations

import pytest

from src.application.assurance.guidance import STPA_STEP_NUMBERING, lookup
from src.domain.assurance.failure_modes import FAILURE_GUIDEWORDS
from src.domain.assurance.uca_guidewords import UCA_GUIDEWORDS


def _text(topic: str) -> str:
    guidance = lookup(topic)
    assert "available_topics" not in guidance, f"{topic} has no guidance: {guidance}"
    return " ".join(str(value) for key, value in guidance.items() if key != "standards")


# ── The UCA guidewords ────────────────────────────────────────────────────────


def test_the_uca_guidance_names_every_guideword_the_software_applies() -> None:
    text = _text("stpa-ucas").lower()

    missing = [word.label for word in UCA_GUIDEWORDS if word.label.lower() not in text]

    assert missing == [], f"guidance does not teach: {missing}"


def test_the_uca_guidance_walks_exactly_as_many_guidewords_as_the_vocabulary_has() -> None:
    """Counted from the numbering an analyst is walked through, so the word form stays free prose.

    Scoped to `how`, which is where the walkthrough lives: the step-numbering statement also carries
    parenthesised numbers, and counting across the whole payload counts those too.
    """
    walkthrough = str(lookup("stpa-ucas")["how"])

    assert f"({len(UCA_GUIDEWORDS)})" in walkthrough
    assert f"({len(UCA_GUIDEWORDS) + 1})" not in walkthrough
    assert "Four types" not in _text("stpa-ucas"), "the pre-refinement count, which under-enumerates"


def test_the_uca_guidance_asks_each_guideword_as_a_question() -> None:
    """The questions are what an analyst actually works through, so they are the guidance."""
    text = _text("stpa-ucas")

    for word in UCA_GUIDEWORDS:
        assert word.question in text, word.slug


def test_the_uca_guidance_says_why_the_second_guideword_was_split() -> None:
    """A refinement that arrives unexplained reads as a mistake, and gets 'corrected' back."""
    text = _text("stpa-ucas").lower()

    assert "split" in text
    assert "unsafe context" in text
    assert "incorrectly" in text


def test_the_guideword_only_applying_to_held_actions_says_so() -> None:
    text = _text("stpa-ucas").lower()
    continuous = [word for word in UCA_GUIDEWORDS if word.continuous_only]

    assert continuous, "the vocabulary no longer marks one — this test's premise changed"
    assert "continuous control actions only" in text


# ── The failure guidewords, held the same way ─────────────────────────────────


def test_the_failure_mode_guidance_names_every_failure_guideword() -> None:
    """Latent rather than broken today, and asserted so it stays that way."""
    text = _text("fmea-failure-modes").lower()

    missing = [word.label for word in FAILURE_GUIDEWORDS if word.label.lower() not in text]

    assert missing == [], f"guidance does not teach: {missing}"


# ── Loss scenarios ────────────────────────────────────────────────────────────


def test_loss_scenarios_have_a_topic_of_their_own() -> None:
    """The step where STPA stops auditing its register had no guidance at all."""
    guidance = lookup("stpa-loss-scenarios")

    assert guidance["topic"] == "stpa-loss-scenarios"
    assert "available_topics" not in guidance


@pytest.mark.parametrize("scenario_type", ["unsafe-control", "improper-execution"])
def test_the_loss_scenario_guidance_covers_both_handbook_classes(scenario_type: str) -> None:
    """Type b explains a hazard with no UCA involved; a topic teaching only type a hides it."""
    assert scenario_type in _text("stpa-loss-scenarios")


def test_the_loss_scenario_guidance_names_the_edges_a_scenario_carries() -> None:
    text = _text("stpa-loss-scenarios")

    for edge in ("explains", "concerns", "derives"):
        assert f"`{edge}`" in text, edge


# ── Step numbering ────────────────────────────────────────────────────────────


def test_every_stpa_topic_states_how_its_numbering_maps_to_the_handbook() -> None:
    for topic in (
        "stpa-losses",
        "stpa-hazards",
        "stpa-control-structure",
        "stpa-ucas",
        "stpa-constraints",
        "stpa-loss-scenarios",
        "cast-investigation",
    ):
        assert lookup(topic).get("step_numbering") == STPA_STEP_NUMBERING, topic


def test_a_non_stpa_topic_carries_no_numbering_statement() -> None:
    """It is a fact about one decomposition, not a preamble to every answer."""
    assert "step_numbering" not in lookup("grc-risk")


def test_the_numbering_statement_names_both_counts() -> None:
    assert "six steps" in STPA_STEP_NUMBERING
    assert "four" in STPA_STEP_NUMBERING


#: The decomposition as `docs/04-assurance/methods.md` states it. The guidance disagreed with the
#: documentation when the loss-scenario topic was added — it numbered constraints 5 and scenarios 6,
#: while the docs and the ontology both put scenarios first (`loss-scenario --derives--> constraint`).
#: Two numberings of one method is worse than either, so they are held together here.
DOCUMENTED_STEPS = {
    "stpa-losses": 1,
    "stpa-hazards": 2,
    "stpa-control-structure": 3,
    "stpa-ucas": 4,
    "stpa-loss-scenarios": 5,
    "stpa-constraints": 6,
}


@pytest.mark.parametrize(("topic", "number"), sorted(DOCUMENTED_STEPS.items()))
def test_each_step_carries_the_number_the_documentation_gives_it(topic: str, number: int) -> None:
    assert f"Step {number}" in str(lookup(topic)["step"]), lookup(topic)["step"]


def test_scenarios_are_numbered_before_the_constraints_they_derive() -> None:
    """The ontology's edge direction is the reason: a scenario derives a constraint, not the reverse."""
    assert DOCUMENTED_STEPS["stpa-loss-scenarios"] < DOCUMENTED_STEPS["stpa-constraints"]
    assert "scenario" in str(lookup("stpa-constraints")["how"]).lower()
