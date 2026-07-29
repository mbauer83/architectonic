"""A safety or security constraint must state what enforces it.

The rule was specified when the constraint vocabulary was designed — an accountable owner *and*
either a refined requirement whose realization is the control measure, or a justified
enforcement statement — but only the owner half was ever built. The second limb had no consumer
anywhere, which is why the attribute that was meant to carry it stayed empty: it promised a
state vocabulary where the design wanted prose.

Without the rule, a safety constraint can exist with nothing enforcing it and nothing noticing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.verification.assurance_verifier import verify_store
from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore

_CODE = "E510"


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SQLCipherAssuranceStore:
    from src.infrastructure.assurance import _credential_store as creds

    monkeypatch.setattr(creds, "get", lambda _account: "0" * 64)
    opened = SQLCipherAssuranceStore(tmp_path / "store.db")
    opened.unlock()
    return opened


def _codes(store: SQLCipherAssuranceStore) -> list[str]:
    return [issue.code for issue in verify_store(store).issues]


def _constraint(store: SQLCipherAssuranceStore, **kwargs: object) -> str:
    return store.create_node(
        "assurance-constraint",
        "Untrusted input must not reach the renderer carrying file directives",
        concern_class="security",
        **kwargs,
    )


class TestTheFindingFires:
    def test_with_neither_a_requirement_reference_nor_a_justification(
        self, store: SQLCipherAssuranceStore
    ) -> None:
        _constraint(store)

        assert _CODE in _codes(store)

    def test_a_whitespace_only_justification_does_not_count(
        self, store: SQLCipherAssuranceStore
    ) -> None:
        _constraint(store, attributes={"enforcement_justification": "   "})

        assert _CODE in _codes(store)

    def test_it_is_a_hard_finding_rather_than_informational(
        self, store: SQLCipherAssuranceStore
    ) -> None:
        _constraint(store)

        assert _CODE in [issue.code for issue in verify_store(store).errors]


class TestTheFindingIsSatisfied:
    def test_by_a_justification(self, store: SQLCipherAssuranceStore) -> None:
        _constraint(store, attributes={
            "enforcement_justification": "A boundary validator in the diagram write path rejects the directives.",
        })

        assert _CODE not in _codes(store)

    def test_by_refining_an_architecture_requirement(self, store: SQLCipherAssuranceStore) -> None:
        node_id = _constraint(store)
        store.register_arch_ref(node_id, "REQ@1777135513.nnvsra", "refines-requirement")

        assert _CODE not in _codes(store)

    def test_an_unrelated_reference_type_does_not_satisfy_it(
        self, store: SQLCipherAssuranceStore
    ) -> None:
        """Binding a constraint to some entity says nothing about what enforces it."""
        node_id = _constraint(store)
        store.register_arch_ref(node_id, "APP@1777293133.OYEmP1", "binds-to")

        assert _CODE in _codes(store)


class TestScope:
    def test_an_operational_constraint_is_not_required_to_state_enforcement(
        self, store: SQLCipherAssuranceStore
    ) -> None:
        store.create_node(
            "assurance-constraint", "Exports should complete within the batch window",
            concern_class="operational",
        )

        assert _CODE not in _codes(store)

    def test_the_attribute_is_read_from_the_stored_blob(
        self, store: SQLCipherAssuranceStore
    ) -> None:
        """Guards the reader, not the rule: the value lives in the JSON attribute column."""
        node_id = _constraint(store, attributes={"enforcement_justification": "Enforced at the boundary."})
        stored = store.get_node(node_id)

        assert stored is not None
        assert json.loads(str(stored["attributes_json"]))["enforcement_justification"]
