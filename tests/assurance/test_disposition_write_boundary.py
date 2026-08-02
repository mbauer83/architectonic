"""A constraint's disposition is rejected at the write boundary unless it is in the vocabulary.

Before this, `disposition` was a plain text column written straight through by all four store
backends, so any spelling reached the store. That is why the safety-subordination safeguard could
not fire: it matches `accepted` exactly, and the constraints in the store read something else.
These tests pin both halves — the refusal, and the safeguard firing once only real values get in.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.application.assurance import mutations as mut
from tests.assurance.test_assurance_mutations import _FakeArchive, _FakeStore


def _constraint(store: Any, disposition: str) -> str:
    node_id: str = store.create_node(
        "assurance-constraint", "The renderer must reject non-managed directives",
        concern_class="safety", disposition=disposition,
    )
    return node_id


class TestRefusal:
    def test_creating_with_a_value_outside_the_vocabulary_is_refused(self) -> None:
        result = mut.create_node(
            _FakeStore(), _FakeArchive(),
            node_type="assurance-constraint", name="SC", disposition="mitigated",
        )

        assert isinstance(result, mut.MutationRejected)
        assert result.field == "disposition"
        assert result.value == "mitigated"

    def test_editing_to_a_value_outside_the_vocabulary_is_refused(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()
        node_id = _constraint(store, "alarp-justified")

        result = mut.edit_node(store, archive, node_id=node_id, disposition="mitigated")

        assert isinstance(result, mut.MutationRejected)
        assert store.get_node(node_id)["disposition"] == "alarp-justified"

    def test_a_refused_write_leaves_no_audit_entry(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()

        mut.create_node(
            store, archive, node_type="assurance-constraint", name="SC", disposition="transfer",
        )

        assert archive.entries == []

    @pytest.mark.verifies("REQ@1780655839.IOPvsf")
    def test_a_risk_treatment_value_does_not_pass_as_a_disposition(self) -> None:
        result = mut.create_node(
            _FakeStore(), _FakeArchive(),
            node_type="assurance-constraint", name="SC", disposition="mitigate",
        )

        assert isinstance(result, mut.MutationRejected)


class TestAcceptance:
    def test_a_member_of_the_vocabulary_is_written(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()

        result = mut.create_node(
            store, archive, node_type="assurance-constraint", name="SC",
            disposition="controlled-with-evidence",
        )

        assert isinstance(result, mut.MutationOk)
        node_id = str(result.payload["node_id"])
        assert store.get_node(node_id)["disposition"] == "controlled-with-evidence"

    def test_undecided_is_stored_as_the_empty_field(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()

        result = mut.create_node(
            store, archive, node_type="assurance-constraint", name="SC", disposition="open",
        )

        assert isinstance(result, mut.MutationOk)
        node_id = str(result.payload["node_id"])
        assert store.get_node(node_id)["disposition"] == ""

    def test_an_omitted_disposition_leaves_the_stored_value_alone(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()
        node_id = _constraint(store, "eliminated")

        result = mut.edit_node(store, archive, node_id=node_id, name="Renamed")

        assert isinstance(result, mut.MutationOk)
        assert store.get_node(node_id)["disposition"] == "eliminated"


class TestTheSafeguardNowFires:
    def test_a_safety_constraint_dispositioned_accepted_is_a_hard_finding(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()

        result = mut.create_node(
            store, archive, node_type="assurance-constraint", name="SC",
            concern_class="safety", disposition="accepted",
        )

        assert isinstance(result, mut.MutationOk)
        assert [f for f in result.findings if f["code"] == "E503" and f["severity"] == "error"]

    def test_a_security_constraint_dispositioned_accepted_is_a_hard_finding(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()

        result = mut.create_node(
            store, archive, node_type="assurance-constraint", name="SC",
            concern_class="security", disposition="accepted",
        )

        assert isinstance(result, mut.MutationOk)
        assert [f for f in result.findings if f["code"] == "E503"]

    def test_an_operational_constraint_may_be_accepted(self) -> None:
        store, archive = _FakeStore(), _FakeArchive()

        result = mut.create_node(
            store, archive, node_type="assurance-constraint", name="SC",
            concern_class="operational", disposition="accepted",
        )

        assert isinstance(result, mut.MutationOk)
        assert not [f for f in result.findings if f["code"] == "E503"]
