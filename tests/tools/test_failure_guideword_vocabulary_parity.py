"""The failure guideword vocabulary is defined twice — once per language — and must not diverge.

The Python side owns it: the attribute-schema enum, the matrix columns and the authoring guidance
all derive from `src/domain/assurance/failure_modes.py`. The frontend cannot import Python, so it keeps its
own copy, and this test is what keeps that copy honest.

The risk is not hypothetical here. The store's type columns carry no enum constraint, so a value
authored against a divergent frontend vocabulary would be accepted and then silently dropped by
every surface that did not recognise it — which is exactly what happened to the parallel STPA
vocabulary when it existed in six places in three variants.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.domain.assurance.failure_modes import FAILURE_GUIDEWORD_SLUGS, FAILURE_GUIDEWORDS, label_for
from src.domain.repository.repo_default_assurance_schemata import ASSURANCE_ATTRIBUTE_SCHEMATA

_FRONTEND = Path(__file__).resolve().parents[2] / "tools/gui/src/ui/lib/failureGuidewords.ts"


def _frontend_entries() -> list[tuple[str, str]]:
    source = _FRONTEND.read_text(encoding="utf-8")
    return re.findall(r"\{\s*slug:\s*'([^']+)',\s*label:\s*'([^']+)'\s*\}", source)


class TestTheTwoCopiesAgree:
    def test_the_frontend_copy_exists(self) -> None:
        """Guards the rest of this file against passing vacuously if the file is renamed."""
        assert _FRONTEND.is_file()

    def test_the_slugs_match_in_the_same_order(self) -> None:
        """Order matters as well as membership: it is the order an analyst is walked through."""
        assert [slug for slug, _ in _frontend_entries()] == list(FAILURE_GUIDEWORD_SLUGS)

    def test_the_labels_match(self) -> None:
        for slug, label in _frontend_entries():
            assert label == label_for(slug), f"{slug} reads differently in the two copies"

    def test_the_shipped_schema_enum_matches_too(self) -> None:
        """The third place the vocabulary appears, and the one a store value is validated against."""
        schema = ASSURANCE_ATTRIBUTE_SCHEMATA["attributes.failure-mode.schema.json"]
        declared = schema["properties"]["failure_type"]["enum"]

        assert declared == list(FAILURE_GUIDEWORD_SLUGS)

    def test_there_are_five(self) -> None:
        assert len(FAILURE_GUIDEWORDS) == 5
