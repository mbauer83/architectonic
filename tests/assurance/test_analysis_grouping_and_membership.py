"""Filing, authorship and participation are three different things.

An assurance node used to belong to exactly one analysis, via `assurance_nodes.analysis_id`.
That single column had to answer two unrelated questions at once — *who made this* and *who
uses this* — and answering both with one value forbids the synergy that makes running two
methods worthwhile: an FMEA cannot enumerate failure modes against the control-structure nodes
an STPA identified without copying them, and the copies then drift.

So there are now three relations, and these tests hold them apart:

* **group → analysis** — filing. Flat, and deleting a folder never deletes its contents.
* **node.analysis_id** — authorship. Single-valued, the analysis that produced the node.
* **analysis_members** — participation. Many-to-many, how one method draws on another's work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
from src.infrastructure.assurance.lifecycle import init_store


@pytest.fixture
def store(tmp_path: Path) -> SQLCipherAssuranceStore:
    """A real store on a temp path. The credential backend is the suite's in-memory fake — see
    tests/conftest.py; nothing here may reach a developer's keychain."""
    db_path = tmp_path / "store.db"
    init_store(db_path)
    opened = SQLCipherAssuranceStore(db_path)
    opened.unlock()
    yield opened
    opened.lock()


class TestGroupsFileAnalyses:
    def test_a_created_group_is_listed(self, store: SQLCipherAssuranceStore) -> None:
        group_id = store.create_group("Platform safety", "Analyses of the platform itself")

        listed = {str(g["group_id"]): str(g["name"]) for g in store.list_groups()}
        assert listed[group_id] == "Platform safety"

    def test_an_analysis_can_be_filed_into_a_group(self, store: SQLCipherAssuranceStore) -> None:
        group_id = store.create_group("Platform safety")
        analysis_id = store.create_analysis("Key availability", "STPA")

        store.update_analysis(analysis_id, group_id=group_id)

        assert str(store.get_analysis(analysis_id)["group_id"]) == group_id

    def test_deleting_a_group_unfiles_its_analyses_rather_than_deleting_them(
        self, store: SQLCipherAssuranceStore,
    ) -> None:
        """Filing and content are the same gesture in a UI. They must not be in the store: a
        hazard analysis is not disposable because the folder holding it was."""
        group_id = store.create_group("Platform safety")
        analysis_id = store.create_analysis("Key availability", "STPA")
        store.update_analysis(analysis_id, group_id=group_id)

        store.delete_group(group_id)

        survivor = store.get_analysis(analysis_id)
        assert survivor is not None, "deleting a group destroyed the analysis inside it"
        assert survivor["group_id"] is None

    def test_an_analysis_needs_no_group(self, store: SQLCipherAssuranceStore) -> None:
        """Filing is optional; an analysis is meaningful before anyone decides where it lives."""
        analysis_id = store.create_analysis("Unfiled", "CAST")

        assert store.get_analysis(analysis_id)["group_id"] is None


class TestParticipationIsNotAuthorship:
    def test_a_node_can_take_part_in_an_analysis_that_did_not_author_it(
        self, store: SQLCipherAssuranceStore,
    ) -> None:
        # The STPA→FMEA case: the control structure an STPA identified is exactly the item list
        # an FMEA enumerates against.
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Component failure modes", "FMEA")
        node_id = store.create_node(
            "control-structure-node", "Credential backend", analysis_id=stpa,
        )

        store.add_analysis_member(fmea, node_id)

        assert store.list_analysis_members(fmea) == [node_id]
        assert str(store.get_node(node_id)["analysis_id"]) == stpa, "authorship changed"

    def test_participation_does_not_copy_the_node(self, store: SQLCipherAssuranceStore) -> None:
        """The whole point: one entity, seen by both analyses, so it cannot drift."""
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Component failure modes", "FMEA")
        node_id = store.create_node("control-structure-node", "Credential backend", analysis_id=stpa)
        store.add_analysis_member(fmea, node_id)

        store.update_node(node_id, name="Credential backend (DPAPI)")

        assert str(store.get_node(node_id)["name"]) == "Credential backend (DPAPI)"
        assert len(store.list_nodes(node_type="control-structure-node")) == 1

    def test_a_node_reports_every_analysis_drawing_on_it(
        self, store: SQLCipherAssuranceStore,
    ) -> None:
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Component failure modes", "FMEA")
        cast = store.create_analysis("The 2026-07-28 key loss", "CAST")
        node_id = store.create_node("control-structure-node", "Credential backend", analysis_id=stpa)

        store.add_analysis_member(fmea, node_id)
        store.add_analysis_member(cast, node_id)

        assert set(store.list_participating_analyses(node_id)) == {fmea, cast}

    def test_drawing_the_same_node_in_twice_is_not_an_error(
        self, store: SQLCipherAssuranceStore,
    ) -> None:
        """"Make sure this participates" is what callers mean; a duplicate is not news."""
        fmea = store.create_analysis("Component failure modes", "FMEA")
        node_id = store.create_node("control-structure-node", "Credential backend")

        store.add_analysis_member(fmea, node_id)
        store.add_analysis_member(fmea, node_id)

        assert store.list_analysis_members(fmea) == [node_id]

    def test_removing_participation_leaves_the_node_and_its_author_intact(
        self, store: SQLCipherAssuranceStore,
    ) -> None:
        stpa = store.create_analysis("Key availability", "STPA")
        fmea = store.create_analysis("Component failure modes", "FMEA")
        node_id = store.create_node("control-structure-node", "Credential backend", analysis_id=stpa)
        store.add_analysis_member(fmea, node_id)

        store.remove_analysis_member(fmea, node_id)

        assert store.list_analysis_members(fmea) == []
        assert store.get_node(node_id) is not None
        assert str(store.get_node(node_id)["analysis_id"]) == stpa
