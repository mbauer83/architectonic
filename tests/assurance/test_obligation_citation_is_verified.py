"""An obligation says which rule it comes from, and the verifier checks that it does.

Before this, three spellings of the citation existed and nothing read any of them: an obligation
with no citation, one with a mistyped clause and one written by a wizard nobody had told about the
ontology's form all verified identically. Four findings now tell them apart — W516 (no citation),
W517 (a citation in the attributes that were replaced, with the fix), W518 (a provision its
source's vocabulary does not list) and W519 (a source no vocabulary describes).

The last class runs the store's migration over a real encrypted store, because the migration
connection is not the store's own: it returns rows in another shape, and the entry it appends has
to join the chain the store itself goes on appending to.

Every store here is a temporary one, provisioned from the per-process template under `tmp_path`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

from src.application.assurance.node_attributes import attributes_of  # noqa: E402
from src.application.verification._assurance_rules_obligations import UPGRADE_COMMAND  # noqa: E402
from src.application.verification.assurance_verifier import verify_store  # noqa: E402
from src.domain.assurance.obligation_citation import source_key  # noqa: E402
from src.infrastructure.assurance.reference_vocab import provisions_by_source  # noqa: E402

CITATION_CODES = {"W516", "W517", "W518", "W519"}


@pytest.fixture()
def store(unlocked_store: Any) -> Iterator[Any]:
    yield unlocked_store


def _findings(store: Any, **kwargs: Any) -> dict[str, str]:
    """Citation finding code → its message. One obligation per test, so a code appears once."""
    result = verify_store(store, **kwargs)
    return {issue.code: issue.message for issue in result.issues if issue.code in CITATION_CODES}


class TestAnObligationNamesItsSource:
    def test_one_stating_both_parts_raises_nothing(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"source": "EU AI Act", "provision": "Art. 12"})

        assert _findings(store) == {}

    def test_one_stating_neither_is_told_which_attributes_to_set(self, store: Any) -> None:
        store.create_node("obligation", "O")

        message = _findings(store)["W516"]

        assert "`source`" in message
        assert "`provision`" in message

    def test_one_missing_only_the_provision_is_told_only_that(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"source": "GDPR"})

        message = _findings(store)["W516"]

        assert "`provision`" in message
        assert "`source`" not in message

    def test_the_finding_does_not_block_sign_off(self, store: Any) -> None:
        store.create_node("obligation", "O")

        assert verify_store(store).valid


class TestACitationInASupersededAttribute:
    @pytest.mark.parametrize(
        ("attributes", "named"),
        [({"scheme": "ISO26262", "code": "6-8"}, ("`scheme`", "`code`")), ({"cites": "ISO26262:6-8"}, ("`cites`",))],
    )
    def test_it_is_reported_with_the_attributes_and_the_fix(
        self, store: Any, attributes: dict[str, object], named: tuple[str, ...],
    ) -> None:
        """What a deployment that never ran the upgrade sees."""
        store.create_node("obligation", "O", attributes=attributes)

        findings = _findings(store)

        message = findings["W517"]
        for name in named:
            assert name in message
        assert UPGRADE_COMMAND in message
        assert "`source`" in message
        assert "`provision`" in message

    def test_it_is_one_finding_not_also_a_missing_citation(self, store: Any) -> None:
        """Telling a reader to type a source that is already there, one attribute over, misleads."""
        store.create_node("obligation", "O", attributes={"cites": "ISO26262:6-8"})

        assert set(_findings(store)) == {"W517"}

    def test_the_message_does_not_repeat_the_citation(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"scheme": "SecretFramework", "code": "Clause-99"})

        message = _findings(store)["W517"]

        assert "SecretFramework" not in message
        assert "Clause-99" not in message


class TestAgainstTheReferenceVocabularies:
    def test_without_vocabularies_no_vocabulary_question_is_asked(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"source": "ISO 26262", "provision": "no such clause"})

        assert _findings(store) == {}

    def test_a_listed_provision_of_a_known_source_raises_nothing(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"source": "ISO 26262", "provision": "6-8"})

        assert _findings(store, provisions=provisions_by_source()) == {}

    def test_an_unlisted_provision_of_a_known_source_is_reported_with_what_is_listed(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"source": "ISO 26262", "provision": "6_8"})

        findings = _findings(store, provisions=provisions_by_source())

        assert set(findings) == {"W518"}
        assert "'6_8'" in findings["W518"]
        assert "6-8" in findings["W518"]

    def test_a_source_no_vocabulary_describes_is_accepted_and_said_to_be_unchecked(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"source": "EU AI Act", "provision": "Art. 12"})

        findings = _findings(store, provisions=provisions_by_source())

        assert set(findings) == {"W519"}
        assert "without being checked" in findings["W519"]

    def test_neither_vocabulary_finding_is_more_than_a_statement(self, store: Any) -> None:
        store.create_node("obligation", "A", attributes={"source": "EU AI Act", "provision": "Art. 12"})
        store.create_node("obligation", "B", attributes={"source": "ISO 26262", "provision": "6_8"})

        result = verify_store(store, provisions=provisions_by_source())

        vocabulary = [issue for issue in result.issues if issue.code in {"W518", "W519"}]
        assert {issue.severity for issue in vocabulary} == {"info"}

    def test_an_incomplete_citation_is_not_compared(self, store: Any) -> None:
        store.create_node("obligation", "O", attributes={"source": "ISO 26262"})

        assert set(_findings(store, provisions=provisions_by_source())) == {"W516"}


class TestWhatTheShippedVocabulariesList:
    def test_a_standard_is_found_however_it_is_written(self) -> None:
        listed = provisions_by_source()

        assert "6-8" in listed[source_key("ISO 26262")]
        assert listed[source_key("ISO/SAE 21434")] == listed[source_key("ISO21434")]

    def test_a_classification_level_is_not_a_provision(self) -> None:
        """An integrity level classifies something; nothing is obliged by one."""
        assert "ASIL-D" not in provisions_by_source()[source_key("ISO26262")]

    def test_a_classification_scheme_is_not_a_source(self) -> None:
        """STRIDE lists threat categories and no provisions, so it is absent, not empty."""
        assert source_key("STRIDE") not in provisions_by_source()


class TestMigratingARealStore:
    def test_the_upgrade_step_moves_the_citation_and_the_store_reads_a_whole_chain(self, tmp_path: Path) -> None:
        from src.application.deployment_upgrade.steps.obligation_citation_form import (
            ObligationCitationFormStep,
        )
        from src.domain.repository.operational_upgrade import UpgradeTarget
        from src.infrastructure.assurance import _credential_accounts as accounts
        from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive
        from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
        from src.infrastructure.deployment.database_targets import (
            DatabaseTargetHandle,
            sqlcipher_connection_factory,
        )
        from tests.support.assurance_store_template import provision_store

        db_path = provision_store(tmp_path / "store.db")
        store = SQLCipherAssuranceStore(db_path)
        store.unlock()
        archive = SQLCipherAssuranceArchive(store.unlocked_connection)
        by_wizard = str(store.create_node("obligation", "A", attributes={"scheme": "ISO26262", "code": "6-8"}))
        archive.append("CREATE", node_id=by_wizard, payload={"node_type": "obligation"})
        by_agent = str(store.create_node("obligation", "B", attributes={"cites": "EU-AI-Act:Art-12", "status": "x"}))
        store.lock()

        key = accounts.read(accounts.DB_KEY, db_path)
        assert key is not None
        handle = DatabaseTargetHandle(
            target=UpgradeTarget(
                kind="assurance_sqlcipher",
                stable_id=f"assurance_sqlcipher:{db_path}",
                display_location=str(db_path),
                current_version=None,
                credential_requirement="sqlcipher_key",
            ),
            connect=sqlcipher_connection_factory(db_path, key),
            inspectable=True,
            path=db_path,
        )
        step = ObligationCitationFormStep()
        view = handle.view()
        uow = handle.begin()
        step.apply(view, uow, step.detect(view))
        uow.commit()

        store.unlock()
        try:
            archive = SQLCipherAssuranceArchive(store.unlocked_connection)
            assert attributes_of(store.get_node(by_wizard)) == {"source": "ISO26262", "provision": "6-8"}
            assert attributes_of(store.get_node(by_agent)) == {
                "source": "EU-AI-Act", "provision": "Art-12", "status": "x",
            }
            migrated = [e for e in archive.list_entries() if "upgrade_step" in str(e["payload_json"])]
            assert sorted(str(e["node_id"]) for e in migrated) == sorted([by_wizard, by_agent])
            archive.append("UPDATE", node_id=by_wizard, payload={"updated_fields": ["name"]})
            assert archive.verify_chain(), "the store's next entry must chain onto the migration's"
            assert "W517" not in {issue.code for issue in verify_store(store).issues}
            assert step.detect(handle.view()) == []
        finally:
            store.lock()
