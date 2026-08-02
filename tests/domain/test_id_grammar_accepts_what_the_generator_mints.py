"""The id parser accepts every id the id generator can produce.

Two halves of one convention, in two modules, and they disagreed for a release. `generate_entity_id`
draws its short random key from ``string.ascii_letters + string.digits + "-_"``; `_ENTITY_ID_RE` in
`src/domain/artifact_id.py` — the module whose docstring calls itself "Canonical identity helpers" and
warns that a restated charset makes "the two grammars drift apart" — spelled that key `[A-Za-z0-9-]+`,
without the underscore.

So about **9%** of ids the product mints were rejected by the product's own parser: six characters from
a 64-symbol alphabet, 1 − (63/64)⁶. Every other grammar in the codebase already allowed the underscore,
including the verifier's own `ENTITY_ID_RE` and all three shipped frontmatter JSON Schemas, so the
canonical module was the one that had drifted away from its dependents.

**What that cost, and why nobody saw it.** `parse_entity_id` raises, and `artifact_admin_reindex(scope=
"entity")` is its only caller — loud but rare. `is_entity_id` does not raise: it returns False, so
`canonical_entity_key` returns the *full* id where it should return the stable short one, and its
docstring already spells out the consequence — "the same element is listed twice, or a record filed
under one form is invisible to a reader using the other". Around thirty call sites take that key, most
of them joining assurance nodes to architecture entities, so roughly one entity in eleven joined on the
wrong form of its own identity. Silently, and only for the entities whose random key happened to contain
an underscore, which is why no fixed example ever failed.

It surfaced from a test about something else entirely — a requirement's ID-convention claim — which
failed on one run in three. That is the shape of this defect: intermittent by construction.

The tests below are written against the generator's **alphabet**, not against sampled output, because
sampling is what made this invisible. If the alphabet gains a character, these fail; if the grammar
loses one, these fail.
"""

from __future__ import annotations

import re

import pytest

from src.application.modeling.artifact_write import (
    _ID_ALPHABET,
    generate_diagram_id,
    generate_entity_id,
)
from src.domain.artifact_id import (
    RANDOM_KEY_PATTERN,
    canonical_entity_key,
    is_entity_id,
    parse_entity_id,
    stable_id,
)


def test_every_character_the_generator_can_draw_is_one_the_grammar_accepts() -> None:
    """The property, stated over the alphabet rather than over samples.

    A per-character check rather than one whole-string check, so a failure names the character that
    disagrees instead of only reporting that some string did not parse.
    """
    random_key = re.compile(f"^{RANDOM_KEY_PATTERN}$")
    rejected = [character for character in _ID_ALPHABET if not random_key.match(character)]

    assert rejected == [], (
        f"the id generator can mint these characters into a random key and the canonical grammar "
        f"rejects them: {rejected!r}"
    )


@pytest.mark.parametrize("character", sorted(set(_ID_ALPHABET)))
def test_an_id_whose_random_key_holds_this_character_parses(character: str) -> None:
    """Every alphabet character, in the position the generator puts it, through the real parser.

    The underscore is the one that was broken; parameterising over all of them is what stops the next
    alphabet change from needing this file to be remembered.
    """
    identifier = f"APP@1700000000.ab{character}cde.some-slug"

    assert is_entity_id(identifier), identifier
    assert parse_entity_id(identifier).random == f"ab{character}cde"


@pytest.mark.parametrize("character", sorted(set(_ID_ALPHABET)))
def test_the_stable_key_of_such_an_id_is_its_short_form(character: str) -> None:
    """The silent half. `canonical_entity_key` falling through to the full id is not an error anywhere —
    it is two records that should have been one, in whichever store asked."""
    short = f"APP@1700000000.ab{character}cde"
    full = f"{short}.some-slug"

    assert canonical_entity_key(full) == short, full
    assert canonical_entity_key(short) == short, short
    assert stable_id(full) == short, full


def test_ids_the_generator_actually_produces_parse() -> None:
    """A smaller, blunter check against real output, for the case where the alphabet constant is right
    and the *assembly* is not. Many draws rather than one, because one has a 91% chance of passing."""
    for index in range(400):
        entity = generate_entity_id("APP", f"probe {index}")
        diagram = generate_diagram_id("archimate-application", f"probe {index}")
        for identifier in (entity, diagram):
            assert is_entity_id(identifier), identifier
            assert canonical_entity_key(identifier) == stable_id(identifier), identifier


def test_the_verifier_and_the_canonical_module_agree_about_the_random_key() -> None:
    """One grammar, two consumers — the drift this whole file is about.

    The verifier's pattern is stricter in one respect (it demands the slug), so equality of the two
    regexes is the wrong assertion; what must hold is that they share the random-key fragment.
    """
    from src.application.verification.artifact_verifier_types import ENTITY_ID_RE

    assert RANDOM_KEY_PATTERN in ENTITY_ID_RE.pattern
    for character in sorted(set(_ID_ALPHABET)):
        assert ENTITY_ID_RE.match(f"APP@1700000000.ab{character}cde.some-slug"), character
