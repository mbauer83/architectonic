"""The STPA guideword vocabulary is defined twice — once per language — and must not diverge.

It used to be written out in six places in three mutually inconsistent variants: the attribute
schema's enum, the matrix columns, the wizard, the authoring form (which offered
`commission`/`omission`/`wrong-duration`), and two guidance texts. The store's `uca_type` column has
no enum constraint, so a UCA authored through that form was accepted and then silently dropped by the
matrix, which only reads the columns it knows. Every one of those sites now derives from
`src/domain/assurance/uca_guidewords.py`, except the frontend's own copy, which cannot import Python — this
test is what keeps that copy honest.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.domain.assurance.uca_guidewords import (
    LEGACY_GUIDEWORD_SLUGS,
    UCA_GUIDEWORD_SLUGS,
    UCA_GUIDEWORDS,
    canonical_guideword,
    label_for,
)
from src.domain.repository.repo_default_assurance_schemata import ASSURANCE_ATTRIBUTE_SCHEMATA

_FRONTEND_VOCABULARY = Path(__file__).resolve().parents[2] / "tools/gui/src/ui/lib/ucaGuidewords.ts"


def _frontend_entries(pattern: str) -> list[tuple[str, str]]:
    text = _FRONTEND_VOCABULARY.read_text(encoding="utf-8")
    block = re.search(pattern, text, re.DOTALL)
    assert block is not None, f"could not find {pattern!r} in {_FRONTEND_VOCABULARY.name}"
    return re.findall(r"'([^']+)'\s*:\s*'([^']+)'|slug:\s*'([^']+)',\s*label:\s*'([^']+)'", block.group(1))


def test_frontend_lists_the_same_guidewords_in_the_same_order() -> None:
    """Order is part of the contract: it is the matrix's column order and the wizard's step order."""
    pairs = _frontend_entries(r"UCA_GUIDEWORDS[^=]*=\s*\[(.*?)\]\s*as const")
    frontend = [(slug, label) for _k, _v, slug, label in pairs if slug]

    assert frontend == [(g.slug, g.label) for g in UCA_GUIDEWORDS]


def test_frontend_maps_the_same_legacy_guidewords() -> None:
    pairs = _frontend_entries(r"LEGACY_SLUGS[^=]*=\s*\{(.*?)\}")
    frontend = {k: v for k, v, _s, _l in pairs if k}

    assert frontend == LEGACY_GUIDEWORD_SLUGS


def test_the_attribute_schema_enum_is_the_vocabulary() -> None:
    schema = ASSURANCE_ATTRIBUTE_SCHEMATA["attributes.unsafe-control-action.schema.json"]

    assert schema["properties"]["uca_type"]["enum"] == list(UCA_GUIDEWORD_SLUGS)


class TestTheSplit:
    def test_providing_is_two_guidewords_not_one(self) -> None:
        """A wrong context is answered by a guard on state, a wrong command by validating the
        command — an analysis that cannot tell them apart cannot say which constraint it needs."""
        assert "provided" not in UCA_GUIDEWORD_SLUGS
        assert "provided-in-unsafe-context" in UCA_GUIDEWORD_SLUGS
        assert "provided-incorrectly" in UCA_GUIDEWORD_SLUGS

    def test_the_four_handbook_guidewords_are_all_still_represented(self) -> None:
        assert UCA_GUIDEWORD_SLUGS == (
            "not-provided",
            "provided-in-unsafe-context",
            "provided-incorrectly",
            "wrong-timing",
            "wrong-duration",
        )

    def test_only_the_duration_guideword_is_marked_continuous_only(self) -> None:
        """Guideword 4 applies to a control action held over time; the rest are discrete."""
        continuous = [g.slug for g in UCA_GUIDEWORDS if g.continuous_only]
        assert continuous == ["wrong-duration"]

    def test_every_guideword_states_the_question_it_asks(self) -> None:
        for guideword in UCA_GUIDEWORDS:
            assert guideword.question.endswith("?"), guideword.slug
            assert guideword.label and guideword.label[0].isupper()


class TestLegacyValues:
    def test_the_pre_split_value_reads_as_the_unsafe_context_half(self) -> None:
        """`provided` meant "provided when it should not be", which is the context reading. Nothing
        maps to the incorrect-command half — it had no home before, so no analyst decided it."""
        assert canonical_guideword("provided") == "provided-in-unsafe-context"
        assert "provided-incorrectly" not in LEGACY_GUIDEWORD_SLUGS.values()

    def test_the_duration_guideword_is_named_as_the_parallel_of_wrong_timing(self) -> None:
        """Both ask about *when* — one about the instant, one about how long — so they are named
        alike. `stopped-too-soon` named only one of the two symptoms it covers."""
        assert "wrong-duration" in UCA_GUIDEWORD_SLUGS
        assert "stopped-too-soon" not in UCA_GUIDEWORD_SLUGS
        assert canonical_guideword("stopped-too-soon") == "wrong-duration"

    def test_the_authoring_form_variants_map_to_their_meaning(self) -> None:
        assert canonical_guideword("omission") == "not-provided"
        assert canonical_guideword("commission") == "provided-in-unsafe-context"
        assert canonical_guideword("stopped-too-soon") == "wrong-duration"

    def test_a_current_value_is_left_alone(self) -> None:
        for slug in UCA_GUIDEWORD_SLUGS:
            assert canonical_guideword(slug) == slug

    def test_an_unknown_value_is_shown_rather_than_guessed_at(self) -> None:
        """A UCA carrying a guideword this software does not know is still a finding."""
        assert canonical_guideword("invented-by-hand") == "invented-by-hand"
        assert label_for("invented-by-hand") == "invented-by-hand"
        assert canonical_guideword(None) is None

    def test_a_legacy_value_is_labelled_by_its_current_guideword(self) -> None:
        assert label_for("provided") == "Provided in unsafe context"


def test_the_store_migration_rewrites_every_legacy_value() -> None:
    """The persisted data has to move too, or an existing analysis keeps a value no column reads."""
    from src.infrastructure.assurance._schema import ASSURANCE_SCHEMA_MIGRATIONS

    for legacy, current in LEGACY_GUIDEWORD_SLUGS.items():
        statement = f"UPDATE assurance_nodes SET uca_type = '{current}' WHERE uca_type = '{legacy}'"
        assert statement in ASSURANCE_SCHEMA_MIGRATIONS, legacy
