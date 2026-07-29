"""One filing-and-participation contract, exercised against every store backend that ships.

Parameterized rather than written once against SQLCipher for the reason the factor-assessment
conformance run gives: the port declares these methods, so a backend that does not implement them
breaks the port for whoever is configured to use it — and it breaks it the first time an analyst
files an analysis, not at startup. `isinstance(store, ConfidentialAssuranceStore)` catches a
missing method; only a run like this catches one that is present and wrong.

Two behaviours are easy to implement backwards, and each has its own test here:

* **Deleting a group unfiles its analyses; it never deletes them.** Filing and content are the
  same gesture in a UI and must not be the same gesture in the store.
* **`add_analysis_member` is idempotent.** "Make sure this participates" is what callers mean.

And one distinction the whole design rests on: participation does not touch authorship. A
control-structure node drawn into an FMEA is still the STPA's node, and there is no copy of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.assurance_ports import ConfidentialAssuranceStore
from tests.assurance._pocketbase_stub import StubPocketBaseClient


def _private_git_store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._private_git_store import PrivateGitAssuranceStore

    store = PrivateGitAssuranceStore(tmp_path / "assurance-repo")
    store.unlock()
    return store


def _encrypted_private_git_store(tmp_path: Path) -> Any:
    from cryptography.fernet import Fernet  # type: ignore[import-untyped]

    from src.infrastructure.assurance import _credential_store as creds
    from src.infrastructure.assurance._encrypted_private_git_store import (
        EncryptedPrivateGitAssuranceStore,
    )

    creds.set_credential("private-git-encryption-key", Fernet.generate_key().decode())
    store = EncryptedPrivateGitAssuranceStore(tmp_path / ".arch-assurance-git")
    store.unlock()
    return store


def _sqlcipher_store(tmp_path: Path) -> Any:
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    return store


def _pocketbase_store(_tmp_path: Path) -> Any:
    from src.infrastructure.assurance._pocketbase_store import PocketBaseAssuranceStore

    store = PocketBaseAssuranceStore("http://localhost:8090", "admin@example.com", "password")
    store._client = StubPocketBaseClient()  # noqa: SLF001 — stands in for the authenticated client
    return store


_BACKENDS = {
    "sqlcipher": _sqlcipher_store,
    "private-git": _private_git_store,
    "encrypted-private-git": _encrypted_private_git_store,
    "pocketbase": _pocketbase_store,
}


@pytest.fixture(params=sorted(_BACKENDS))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    built = _BACKENDS[request.param](tmp_path)
    yield built
    if hasattr(built, "lock"):
        built.lock()


class TestEveryBackendSatisfiesThePort:
    def test_the_store_satisfies_the_declared_port(self, store: Any) -> None:
        assert isinstance(store, ConfidentialAssuranceStore)


class TestGroupsFileAnalyses:
    def test_a_created_group_is_readable_by_id_and_listed(self, store: Any) -> None:
        group_id = store.create_group("Platform safety", "Analyses of the platform itself")

        assert str(store.get_group(group_id)["name"]) == "Platform safety"
        assert group_id in {str(g["group_id"]) for g in store.list_groups()}

    def test_an_absent_group_reads_as_none(self, store: Any) -> None:
        assert store.get_group("GRP@nothing.here.000000") is None

    def test_groups_are_listed_by_name(self, store: Any) -> None:
        """Filing is a chooser before it is anything else, so the order is the one a reader
        scans."""
        for name in ("Supply chain", "Access control", "Platform safety"):
            store.create_group(name)

        listed = [str(g["name"]) for g in store.list_groups()]
        assert listed == sorted(listed)

    def test_an_analysis_can_be_filed_and_unfiled(self, store: Any) -> None:
        group_id = store.create_group("Platform safety")
        analysis_id = store.create_analysis("Key availability", "STPA")

        store.update_analysis(analysis_id, group_id=group_id)
        assert str(store.get_analysis(analysis_id)["group_id"]) == group_id

        store.update_analysis(analysis_id, group_id=None)
        assert not store.get_analysis(analysis_id)["group_id"]

    def test_deleting_a_group_unfiles_its_analyses_rather_than_deleting_them(
        self, store: Any,
    ) -> None:
        """A hazard analysis is not disposable because the folder holding it was."""
        group_id = store.create_group("Platform safety")
        filed = store.create_analysis("Key availability", "STPA")
        elsewhere = store.create_analysis("Credential backend", "FMEA")
        store.update_analysis(filed, group_id=group_id)

        store.delete_group(group_id)

        assert store.get_group(group_id) is None
        assert store.get_analysis(filed) is not None
        assert not store.get_analysis(filed)["group_id"]
        # An analysis filed somewhere else is untouched by a deletion it has nothing to do with.
        assert store.get_analysis(elsewhere) is not None


class TestParticipationIsSeparateFromAuthorship:
    def test_a_node_participates_without_changing_its_author(self, store: Any) -> None:
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Credential backend", "FMEA")
        node_id = store.create_node(
            "control-structure-node", "Credential backend", analysis_id=stpa
        )

        store.add_analysis_member(fmea, node_id)

        assert store.list_analysis_members(fmea) == [node_id]
        # Authorship is untouched, and no copy was made: one node, still the STPA's.
        assert str(store.get_node(node_id)["analysis_id"]) == stpa
        assert len(store.list_nodes()) == 1

    def test_adding_the_same_member_twice_is_idempotent(self, store: Any) -> None:
        fmea = store.create_analysis("Credential backend", "FMEA")
        node_id = store.create_node("control-structure-node", "Credential backend")

        store.add_analysis_member(fmea, node_id)
        store.add_analysis_member(fmea, node_id)

        assert store.list_analysis_members(fmea) == [node_id]

    def test_removing_a_member_leaves_the_node_alone(self, store: Any) -> None:
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Credential backend", "FMEA")
        node_id = store.create_node(
            "control-structure-node", "Credential backend", analysis_id=stpa
        )
        store.add_analysis_member(fmea, node_id)

        store.remove_analysis_member(fmea, node_id)

        assert store.list_analysis_members(fmea) == []
        assert store.get_node(node_id) is not None
        assert str(store.get_node(node_id)["analysis_id"]) == stpa

    def test_removing_a_membership_that_was_never_granted_is_not_an_error(
        self, store: Any,
    ) -> None:
        fmea = store.create_analysis("Credential backend", "FMEA")
        node_id = store.create_node("control-structure-node", "Credential backend")

        store.remove_analysis_member(fmea, node_id)

        assert store.list_analysis_members(fmea) == []

    def test_participation_is_many_to_many(self, store: Any) -> None:
        """One node reasoned over by two methods is the whole point: the synergy is shared items,
        not shared concepts."""
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Credential backend", "FMEA")
        grc = store.create_analysis("Q3 controls", "GRC")
        node_id = store.create_node(
            "control-structure-node", "Credential backend", analysis_id=stpa
        )

        store.add_analysis_member(fmea, node_id)
        store.add_analysis_member(grc, node_id)

        assert set(store.list_participating_analyses(node_id)) == {fmea, grc}

    def test_members_are_listed_per_analysis(self, store: Any) -> None:
        fmea = store.create_analysis("Credential backend", "FMEA")
        other = store.create_analysis("Key availability", "STPA")
        mine = store.create_node("control-structure-node", "Credential backend")
        theirs = store.create_node("control-structure-node", "Key store")
        store.add_analysis_member(fmea, mine)
        store.add_analysis_member(other, theirs)

        assert store.list_analysis_members(fmea) == [mine]
        assert store.list_analysis_members(other) == [theirs]


class TestDeletingANodeRemovesWhatIsKeyedToIt:
    """Deletion has to reach the node's architecture bindings and its memberships.

    Both are keyed by node id and neither was reached: `arch_refs` never declared a foreign key,
    `assurance_analysis_members` was added without one, and SQLite cannot retrofit either onto a
    table that already exists. The observable consequence was a shipped seed whose export named
    14 nodes that no longer existed — created with bindings by the browser suite against the live
    store, then cleaned up by node id alone.

    Parameterized across every backend because three of the four have no cascade to fall back on
    even in principle: two write files and one writes over REST.
    """

    def test_deleting_a_node_removes_its_architecture_bindings(self, store: Any) -> None:
        node_id = store.create_node("control-structure-node", "Credential backend")
        store.register_arch_ref(node_id, "APP@1712870400.abcdef.credential-store", "binds-to")

        store.delete_node(node_id)

        assert store.list_arch_refs(assurance_node_id=node_id) == []

    def test_deleting_a_node_removes_its_participation(self, store: Any) -> None:
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Credential backend", "FMEA")
        node_id = store.create_node(
            "control-structure-node", "Credential backend", analysis_id=stpa
        )
        store.add_analysis_member(fmea, node_id)

        store.delete_node(node_id)

        assert store.list_analysis_members(fmea) == []
        assert store.list_participating_analyses(node_id) == []

    def test_deletion_leaves_another_nodes_bindings_and_participation_alone(
        self, store: Any,
    ) -> None:
        """The blast radius is one node. A cascade that over-reaches is the worse bug of the
        two, because nothing surfaces it until the surviving analysis is read."""
        fmea = store.create_analysis("Credential backend", "FMEA")
        doomed = store.create_node("control-structure-node", "Credential backend")
        survivor = store.create_node("control-structure-node", "Key store")
        for node_id in (doomed, survivor):
            store.register_arch_ref(node_id, "APP@1712870400.abcdef.credential-store", "binds-to")
            store.add_analysis_member(fmea, node_id)

        store.delete_node(doomed)

        assert [str(ref["assurance_node_id"]) for ref in store.list_arch_refs()] == [survivor]
        assert store.list_analysis_members(fmea) == [survivor]
        assert store.get_node(survivor) is not None
