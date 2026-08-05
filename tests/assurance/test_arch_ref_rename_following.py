"""An assurance reference follows the architecture artifact it names — when the store is unlocked.

A reference holds the artifact's full id and stays *resolvable* across a rename, because identity is
the `PREFIX@epoch.random` stem. What it stops being is truthful: the reader of a safety argument sees
a name the artifact no longer has. Matching on the stem, as the repository's own referrer rewrites do,
also heals a reference left holding some third, older slug.

The write path must not reach into the confidential tier, so it announces the rename and a registered
follower acts. A locked or unconfigured store yields no follower action and no failure: the rename is
already committed, the references still resolve, and the next rename heals them.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.application.rename_followers import (
    ArtifactRenamed,
    collect_follower_notes,
    register_rename_follower,
    registered_rename_followers,
)
from src.domain.assurance.arch_ref_identity import refs_to_retarget
from tests.support.assurance_backends import ASSURANCE_BACKENDS, BACKEND_NAMES

_OLD = "APP@1712870400.abc123.old-name"
_NEW = "APP@1712870400.abc123.new-name"
_ANCIENT = "APP@1712870400.abc123.something-it-was-called-once"
_OTHER = "APP@1712870400.zzz999.another-component"


class TestWhichRefsARenameSpeaksAbout:
    def test_a_ref_holding_the_previous_slug_is_retargeted(self) -> None:
        (ref,) = refs_to_retarget([{"arch_artifact_id": _OLD}], new_arch_artifact_id=_NEW)

        assert ref["arch_artifact_id"] == _OLD

    def test_a_ref_holding_a_much_older_slug_is_retargeted_too(self) -> None:
        """Keying on the id being renamed *from* would leave this one unreachable forever."""
        assert refs_to_retarget([{"arch_artifact_id": _ANCIENT}], new_arch_artifact_id=_NEW)

    def test_a_ref_already_current_is_left_alone(self) -> None:
        assert refs_to_retarget([{"arch_artifact_id": _NEW}], new_arch_artifact_id=_NEW) == ()

    def test_a_ref_to_a_different_artifact_is_left_alone(self) -> None:
        assert refs_to_retarget([{"arch_artifact_id": _OTHER}], new_arch_artifact_id=_NEW) == ()


class TestTheAnnouncement:
    """Driven through `collect_follower_notes`, which takes its followers.

    A test that registered a throwaway follower could not take it back — the registry is process-local
    and only the composition root writes it — so a broken stand-in would stay registered and every
    later rename in that worker would carry its note.
    """

    _RENAME = ArtifactRenamed(old_artifact_id=_OLD, new_artifact_id=_NEW)

    def test_a_follower_hears_the_rename_and_its_note_is_returned(self) -> None:
        heard: list[ArtifactRenamed] = []

        def follower(rename: ArtifactRenamed) -> tuple[str, ...]:
            heard.append(rename)
            return ("did something",)

        notes = collect_follower_notes([follower], self._RENAME)

        assert [r.new_artifact_id for r in heard] == [_NEW]
        assert "did something" in notes

    def test_a_failing_follower_cannot_fail_the_rename(self) -> None:
        """The rename is committed by the time anyone is told; a lagging tier is not a reason to raise."""

        def broken(_rename: ArtifactRenamed) -> tuple[str, ...]:
            raise RuntimeError("store went away")

        notes = collect_follower_notes([broken], self._RENAME)

        assert any("store went away" in note for note in notes)

    def test_one_follower_failing_does_not_silence_the_others(self) -> None:
        def broken(_rename: ArtifactRenamed) -> tuple[str, ...]:
            raise RuntimeError("store went away")

        def working(_rename: ArtifactRenamed) -> tuple[str, ...]:
            return ("did something",)

        notes = collect_follower_notes([broken, working], self._RENAME)

        assert "did something" in notes


class TestTheAssuranceFollower:
    _RENAME = ArtifactRenamed(old_artifact_id=_OLD, new_artifact_id=_NEW)

    def test_importing_it_registers_it(self) -> None:
        from src.infrastructure.assurance.arch_ref_rename_follower import (
            follow_rename_into_assurance,
        )

        assert follow_rename_into_assurance in registered_rename_followers()

    def test_registration_is_idempotent(self) -> None:
        """The capability sentinel imports the module; nothing may register a second time."""
        from src.infrastructure.assurance.arch_ref_rename_follower import (
            follow_rename_into_assurance,
        )

        before = registered_rename_followers()
        register_rename_follower(follow_rename_into_assurance)

        assert registered_rename_followers() == before

    def test_it_is_silent_without_an_open_store(self) -> None:
        from src.infrastructure.assurance.arch_ref_rename_follower import (
            follow_rename_into_assurance,
        )

        notes = follow_rename_into_assurance(self._RENAME)

        assert notes == () or all("Retargeted" in note for note in notes)


@pytest.fixture(params=BACKEND_NAMES, ids=BACKEND_NAMES)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    yield from ASSURANCE_BACKENDS[request.param](tmp_path)


class TestEveryBackendRetargets:
    """`retarget_arch_refs` is on the port, so all four adapters owe it the same behaviour.

    Parameterised over the shared backend harness rather than the store the application happens to be
    configured with: an adapter that implements it differently breaks it for that deployment only, at
    the moment a rename happens rather than at startup.
    """

    def test_a_ref_under_the_old_slug_now_names_the_new_id(self, store: Any) -> None:
        node = str(store.create_node("loss", "Disclosure of evidence", tlp="TLP:GREEN"))
        store.register_arch_ref(node, _OLD, "refines")

        moved = store.retarget_arch_refs(new_arch_artifact_id=_NEW)

        assert moved == 1
        assert [ref["arch_artifact_id"] for ref in store.list_arch_refs()] == [_NEW]

    def test_retargeting_keeps_the_resolution_it_had(self, store: Any) -> None:
        """The reason the store owns this: a caller deleting and re-registering would lose it."""
        node = str(store.create_node("loss", "Disclosure of evidence", tlp="TLP:GREEN"))
        store.register_arch_ref(node, _OLD, "refines")
        store.mark_arch_ref_resolved(node, _OLD, "refines")

        store.retarget_arch_refs(new_arch_artifact_id=_NEW)

        (ref,) = store.list_arch_refs()
        assert ref["resolved_at"] is not None

    def test_a_ref_to_another_artifact_is_left_alone(self, store: Any) -> None:
        node = str(store.create_node("loss", "Disclosure of evidence", tlp="TLP:GREEN"))
        store.register_arch_ref(node, _OTHER, "refines")

        moved = store.retarget_arch_refs(new_arch_artifact_id=_NEW)

        assert moved == 0
        assert [ref["arch_artifact_id"] for ref in store.list_arch_refs()] == [_OTHER]

    def test_a_ref_already_current_is_not_reported_as_moved(self, store: Any) -> None:
        node = str(store.create_node("loss", "Disclosure of evidence", tlp="TLP:GREEN"))
        store.register_arch_ref(node, _NEW, "refines")

        assert store.retarget_arch_refs(new_arch_artifact_id=_NEW) == 0

    def test_a_ref_holding_a_much_older_slug_heals_too(self, store: Any) -> None:
        node = str(store.create_node("loss", "Disclosure of evidence", tlp="TLP:GREEN"))
        store.register_arch_ref(node, _ANCIENT, "refines")

        assert store.retarget_arch_refs(new_arch_artifact_id=_NEW) == 1
        assert [ref["arch_artifact_id"] for ref in store.list_arch_refs()] == [_NEW]
