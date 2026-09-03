"""A frontmatter field that crosses the engagement/enterprise boundary is spelled in one module.

Two artifact kinds point across that boundary — a `global-artifact-reference`, which proxies an
enterprise artifact, and a `proposed-change`, which proposes an edit to one. Both name their target in
frontmatter, and both are read by the index, the verifier, the write path and the REST state layer:
four layers, none of which may import the others' internals.

**The incident.** `global-artifact-id` was spelled at eight sites in eight modules under four constant
names plus bare literals, and the copies had drifted. `_MemStore` bucketed a reference under its
*stripped* target — twice, in two independently written copies — while `find_existing_gar` compared the
raw value. A reference whose field carried a trailing space was indexed under one key and searched for
under another, so the duplicate check could not see it and would create a second reference to the same
enterprise artifact. The tolerant reading already existed; nothing consulted it.

**Why a literal scan is the right instrument here, where it is the wrong one for a fence.**
`test_frontmatter_has_one_definition.py` inspects the *call* rather than the literal, because three
dashes appear in table separators, in id separators and in prose. These names cannot: `global-artifact-id`
is that field and nothing else. So the exact literal is the evidence, with no false positives to filter
and nothing for a second reader to hide behind — a `.get()`, an `fm[...]`, an f-string in a message all
count, because each is a place the spelling can drift.

This is the register `src/application/modeling/enterprise_reference.py` and `proposed_change.py` exist
to satisfy. It is deliberately narrow: it governs the names that cross the tier boundary, not every
frontmatter key in the ontology.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.source_paths import REPO_ROOT, SRC, TOOLS, python_sources


@dataclass(frozen=True)
class CrossTierVocabulary:
    """One module's field names, and the incident that made it their only home."""

    owner: Path
    names: tuple[str, ...]
    instead: str


VOCABULARIES = (
    CrossTierVocabulary(
        owner=Path("src/application/modeling/enterprise_reference.py"),
        names=(
            "global-artifact-reference",
            "global-artifact-id",
            "global-artifact-type",
            "global-artifact-entity-type",
        ),
        instead=(
            "`src.application.modeling.enterprise_reference`: `enterprise_target` for the artifact a "
            "reference names, `proxies_an_entity` for whether it has a connection surface, and the "
            "`GLOBAL_ARTIFACT_*` constants where the field name itself is needed"
        ),
    ),
    CrossTierVocabulary(
        owner=Path("src/application/modeling/proposed_change.py"),
        names=(
            "proposed-change",
            "proposes-change-to",
            "recorded-edit",
            "base-revision",
            "proposal-state",
        ),
        instead=(
            "`src.application.modeling.proposed_change`: the `PROPOSED_CHANGE_TYPE`, "
            "`PROPOSES_CHANGE_TO`, `RECORDED_EDIT`, `BASE_REVISION` and `PROPOSAL_STATE` constants"
        ),
    ),
)


def _spellings_outside_the_owner(vocabulary: CrossTierVocabulary) -> dict[str, list[str]]:
    offenders: dict[str, list[str]] = {}
    for path in python_sources(SRC, TOOLS):
        relative = path.relative_to(REPO_ROOT)
        if relative == vocabulary.owner:
            continue
        source = path.read_text(encoding="utf-8")
        spelled = sorted(name for name in vocabulary.names if f'"{name}"' in source or f"'{name}'" in source)
        if spelled:
            offenders[str(relative)] = spelled
    return offenders


@pytest.mark.parametrize("vocabulary", VOCABULARIES, ids=lambda v: v.owner.stem)
def test_the_owner_is_where_the_register_says_it_is(vocabulary: CrossTierVocabulary) -> None:
    """Without this, moving the module would make its row vacuously satisfied."""
    assert (REPO_ROOT / vocabulary.owner).is_file(), f"{vocabulary.owner} is not there"


@pytest.mark.parametrize("vocabulary", VOCABULARIES, ids=lambda v: v.owner.stem)
def test_the_owner_actually_declares_every_name_it_claims(vocabulary: CrossTierVocabulary) -> None:
    """A row naming a field its owner does not declare would send callers somewhere that cannot help."""
    source = (REPO_ROOT / vocabulary.owner).read_text(encoding="utf-8")
    missing = [name for name in vocabulary.names if f'"{name}"' not in source]

    assert missing == [], f"{vocabulary.owner} claims but does not declare: {missing}"


@pytest.mark.parametrize("vocabulary", VOCABULARIES, ids=lambda v: v.owner.stem)
def test_nothing_outside_the_owner_spells_the_field_name(vocabulary: CrossTierVocabulary) -> None:
    offenders = _spellings_outside_the_owner(vocabulary)

    assert offenders == {}, (
        "these spell a cross-tier field name themselves, which is how eight sites came to disagree "
        f"about whitespace and the duplicate check stopped seeing its own references. Use "
        f"{vocabulary.instead}. {offenders}"
    )


def test_the_detector_would_catch_a_second_spelling() -> None:
    """The guard is tested rather than trusted: a probe that matched nothing would pass silently."""
    vocabulary = VOCABULARIES[0]
    source = (REPO_ROOT / vocabulary.owner).read_text(encoding="utf-8")

    assert all(f'"{name}"' in source for name in vocabulary.names)
    assert _spellings_outside_the_owner(
        CrossTierVocabulary(owner=Path("does/not/exist.py"), names=vocabulary.names, instead="")
    ), "scanning with no owner excluded must report the owner itself"
