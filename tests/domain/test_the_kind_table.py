"""The kind table states, per kind, what its consumers used to spell as literals of their own.

Each expectation below is one of those literals, written down before it was removed, so that asking
the row is shown to give the answer the `match` gave:

* *verified* — `artifact_verify` took `"entity" | "connection" | "diagram" | "document" | "icon"`
  and turned a scratchpad away;
* *standalone* — the verifier's inventory and the bulk candidate inventory each listed
  `("document", "icon")` as the files verified one at a time, and the bulk inventory took
  `"entity" | "connection" | "diagram"` for the model's own;
* *moves the model generation* — the index bumped it `if any(kind != "scratchpad" …)`;
* *id prefix* — `"SCR"` at the REST route and again at the MCP tool, `"ICO"` beside the icon reference.

`test_the_layout_says_what_kind_of_artifact_a_path_holds` holds the reading of a path, which this
table now answers; this holds the facts.
"""

from __future__ import annotations

from typing import get_args

import pytest

from src.application.verification.artifact_verifier_types import VerificationFileType
from src.domain.icons.icon_ref import ICON_ID_PREFIX
from src.domain.repository.artifact_kind_consistency import kind_table_contradictions
from src.domain.repository.artifact_location import (
    ARTIFACT_KIND_NAMES,
    ARTIFACT_KINDS,
    ArtifactKindName,
    VerifiedArtifactKindName,
    artifact_kind,
    artifact_kind_at,
    artifact_kind_declared_at,
    is_verified_kind,
    own_id_prefix,
    source_globs,
)

#: name → (verified, verified one file at a time, moves the model generation, own id prefix)
_WHAT_THE_LITERALS_SAID: dict[str, tuple[bool, bool, bool, str | None]] = {
    "entity": (True, False, True, None),
    "connection": (True, False, True, None),
    "diagram": (True, False, True, None),
    "document": (True, True, True, None),
    "icon": (True, True, True, "ICO"),
    "scratchpad": (False, False, False, "SCR"),
}

#: A file of each kind, where the layout puts it.
_A_FILE_OF: dict[ArtifactKindName, tuple[str, ...]] = {
    "entity": ("model/application/component/APP@1.a.x.md", "projects/core/model/a/b/APP@1.a.x.md"),
    "connection": ("model/a/b/APP@1.a.x.outgoing.md", "projects/core/model/a/b/APP@1.a.x.outgoing.md"),
    "diagram": ("diagram-catalog/diagrams/core/ARC@1.a.x.puml", "diagram-catalog/diagrams/core/MAT@1.a.x.md"),
    "document": ("docs/adr/core/ADR@1.a.x.md",),
    "icon": ("diagram-catalog/icons/ICO@1.a.x.md",),
    "scratchpad": ("scratchpads/core/SCR@1.a.x.scratchpad.yaml",),
}


def test_the_table_holds_exactly_the_kinds_that_exist() -> None:
    assert set(ARTIFACT_KIND_NAMES) == set(_WHAT_THE_LITERALS_SAID)
    assert len(ARTIFACT_KIND_NAMES) == len(ARTIFACT_KINDS) == len(set(ARTIFACT_KIND_NAMES))


@pytest.mark.parametrize("name", ARTIFACT_KIND_NAMES)
def test_each_row_states_what_the_literals_did(name: ArtifactKindName) -> None:
    verified, standalone, moves_generation, prefix = _WHAT_THE_LITERALS_SAID[name]
    row = artifact_kind(name)

    assert is_verified_kind(name) is verified
    assert (row.verification != "unverified") is verified
    assert (row.verification == "standalone") is standalone
    assert (row.verification == "with-the-model") is (verified and not standalone)
    assert row.moves_model_generation is moves_generation
    assert row.id_prefix == prefix


def test_the_public_lists_of_names_are_the_table_s() -> None:
    """A `Literal` cannot be computed, so the two that contracts are typed by are held to the rows."""
    assert get_args(ArtifactKindName) == ARTIFACT_KIND_NAMES
    assert get_args(VerifiedArtifactKindName) == tuple(
        kind.name for kind in ARTIFACT_KINDS if kind.verification != "unverified"
    )
    assert get_args(VerificationFileType) == get_args(VerifiedArtifactKindName)


def test_a_kind_s_own_prefix_is_read_from_its_row() -> None:
    assert own_id_prefix("scratchpad") == "SCR"
    assert own_id_prefix("icon") == ICON_ID_PREFIX == "ICO"


@pytest.mark.parametrize("name", [kind.name for kind in ARTIFACT_KINDS if kind.id_prefix is None])
def test_a_kind_whose_ids_take_a_type_s_prefix_has_none_to_give(name: ArtifactKindName) -> None:
    with pytest.raises(LookupError, match="declares no id prefix of its own"):
        own_id_prefix(name)


@pytest.mark.parametrize("name", ARTIFACT_KIND_NAMES)
def test_a_file_where_the_row_puts_it_is_read_as_that_row(name: ArtifactKindName) -> None:
    """The round trip: what a row declares about place and name, read back by the walk over the rows."""
    for relative in _A_FILE_OF[name]:
        assert artifact_kind_at(relative) == name
        assert artifact_kind_declared_at(relative) is artifact_kind(name)


@pytest.mark.parametrize("kind", ARTIFACT_KINDS, ids=lambda kind: kind.name)
def test_a_kind_s_globs_find_its_files_and_only_where_it_may_sit(kind, tmp_path) -> None:
    """Whoever lists a kind's files walks by the row's patterns, so the patterns must agree with the walk.

    Stated over what a row *permits* — every root, every suffix, and a nested directory — rather than
    over the files the shipped layout happens to hold.
    """
    expected = set()
    for root in kind.roots:
        directory = tmp_path.joinpath(*("core" if segment == "*" else segment for segment in root))
        for suffix in kind.suffixes:
            for holder in (directory, directory / "nested"):
                holder.mkdir(parents=True, exist_ok=True)
                (holder / f"X@1.a.x{suffix}").write_text("", encoding="utf-8")
                if kind.placement == "anywhere-below" or holder == directory:
                    expected.add(holder / f"X@1.a.x{suffix}")
        (directory / "stray.txt").write_text("", encoding="utf-8")

    found = {path for pattern in source_globs(kind) for path in tmp_path.glob(pattern)}

    assert expected <= found
    held = {path for path in found if artifact_kind_at(path.relative_to(tmp_path)) == kind.name}
    assert held == {path for path in expected if artifact_kind_at(path.relative_to(tmp_path)) == kind.name}
    assert held, "a kind none of whose declared places holds it is a row the walk never reaches"


def test_the_shipped_table_does_not_contradict_itself() -> None:
    assert kind_table_contradictions(ARTIFACT_KINDS) == []
