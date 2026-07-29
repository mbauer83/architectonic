"""The constraint-disposition vocabulary is defined twice — once per language — and must not diverge.

Four spellings of one field once shipped together: the authoring form offered six values, the
scaffolding schema eight (three of them ISO 31000 risk treatments belonging to a risk's
`treatment`), the store held a ninth that appeared in neither, and nothing validated any of it.
The consequence was a safety control that failed open — the safety-subordination safeguard matches
`accepted` exactly, so every variant slipped past it.

Every site now derives from `src/domain/assurance/constraint_dispositions.py`, except the frontend's own copy,
which cannot import Python — this test is what keeps that copy honest.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.domain.assurance.constraint_dispositions import (
    ACCEPTED,
    CONSTRAINT_DISPOSITION_SLUGS,
    CONSTRAINT_DISPOSITIONS,
    CONTROLLED_WITH_EVIDENCE,
    ELIMINATED,
    DispositionRejection,
    accept_written_value,
    is_absent,
    label_for,
    rank,
)
from src.domain.repository.repo_default_assurance_schemata import ASSURANCE_ATTRIBUTE_SCHEMATA

_FRONTEND_VOCABULARY = (
    Path(__file__).resolve().parents[2] / "tools/gui/src/ui/lib/constraintDispositions.ts"
)


def _frontend_pairs() -> list[tuple[str, str]]:
    text = _FRONTEND_VOCABULARY.read_text(encoding="utf-8")
    block = re.search(r"CONSTRAINT_DISPOSITIONS[^=]*=\s*\[(.*?)\]\s*as const", text, re.DOTALL)
    assert block is not None, f"could not find the vocabulary in {_FRONTEND_VOCABULARY.name}"
    return re.findall(r"slug:\s*'([^']+)',\s*label:\s*'([^']+)'", block.group(1))


def test_frontend_lists_the_same_dispositions_in_the_same_order() -> None:
    """Order is part of the contract: it is the hierarchy of controls, strongest first."""
    assert _frontend_pairs() == [(d.slug, d.label) for d in CONSTRAINT_DISPOSITIONS]


def test_the_attribute_schema_enum_is_the_vocabulary() -> None:
    schema = ASSURANCE_ATTRIBUTE_SCHEMATA["attributes.assurance-constraint.schema.json"]

    assert schema["properties"]["disposition"]["enum"] == list(CONSTRAINT_DISPOSITION_SLUGS)


def test_the_schema_declares_the_ordering_as_a_rank() -> None:
    schema = ASSURANCE_ATTRIBUTE_SCHEMATA["attributes.assurance-constraint.schema.json"]

    assert schema["properties"]["disposition"]["x-scale"] == "ordinal"


class TestWhatTheVocabularyExcludes:
    def test_risk_treatment_values_are_not_dispositions(self) -> None:
        """`mitigate`/`transfer`/`avoid` name what an organisation does about a risk and live on a
        risk's `treatment`. The near-homograph accepted/accept is the likely route by which they
        arrived here."""
        for treatment in ("mitigate", "transfer", "avoid"):
            assert treatment not in CONSTRAINT_DISPOSITION_SLUGS

    def test_undecided_is_the_empty_field_rather_than_a_value(self) -> None:
        assert "open" not in CONSTRAINT_DISPOSITION_SLUGS
        assert is_absent("open")
        assert is_absent("")
        assert is_absent(None)
        assert not is_absent(ACCEPTED.slug)


class TestTheOrdering:
    def test_the_strongest_strategy_ranks_first(self) -> None:
        assert rank(ELIMINATED.slug) == 0
        assert rank(ACCEPTED.slug) == len(CONSTRAINT_DISPOSITIONS) - 1

    def test_weaker_than_controlled_with_evidence_is_a_comparison(self) -> None:
        evidence_rank = rank(CONTROLLED_WITH_EVIDENCE.slug)
        assert evidence_rank is not None
        weaker = [d.slug for d in CONSTRAINT_DISPOSITIONS if (rank(d.slug) or 0) > evidence_rank]
        assert weaker == ["alarp-justified", "accepted"]

    def test_an_unrecognised_value_has_no_rank_rather_than_the_worst_one(self) -> None:
        """A value this software does not know is not thereby the weakest strategy."""
        assert rank("mitigated") is None
        assert label_for("mitigated") == "mitigated"


class TestTheWriteBoundary:
    def test_a_member_of_the_vocabulary_is_stored_as_written(self) -> None:
        assert accept_written_value(ELIMINATED.slug) == ELIMINATED.slug

    def test_an_absence_spelling_normalises_to_the_empty_field(self) -> None:
        assert accept_written_value("open") == ""
        assert accept_written_value("  ") == ""

    def test_an_omitted_value_leaves_the_field_alone(self) -> None:
        assert accept_written_value(None) is None

    def test_an_unknown_value_is_refused_rather_than_stored(self) -> None:
        rejection = accept_written_value("mitigated")

        assert isinstance(rejection, DispositionRejection)
        assert "mitigated" in rejection.message
        assert ELIMINATED.slug in rejection.message

    def test_a_risk_treatment_value_cannot_be_stored_as_a_disposition(self) -> None:
        assert isinstance(accept_written_value("mitigate"), DispositionRejection)
