"""A store written before `source` and `provision` holds obligation citations nothing reads.

The step moves them, and three things about how it does so are held here: that it writes an entry
in the audit archive for every obligation it rewrites, in the same transaction, and that the chain
still verifies; that the entry names attributes and never the citation; and that a `cites` with no
reading is left where it is and reported.

The store here is a plain SQLite file carrying the two tables the step touches, in the store's own
DDL for the archive — the step reads and writes through the deployment upgrade's migration
connection, which never opens the store adapter, so no confidential store is involved.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.application.deployment_upgrade.ports import build_operational_registry
from src.application.deployment_upgrade.steps.obligation_citation_form import (
    ObligationCitationFormStep,
)
from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive
from src.infrastructure.assurance._schema import ARCHIVE_ONLY_SCHEMA_SQL
from src.infrastructure.deployment.database_targets import DatabaseTargetHandle

_NODES = """
CREATE TABLE assurance_nodes (
    node_id         TEXT PRIMARY KEY,
    node_type       TEXT NOT NULL,
    name            TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}'
);
"""

Row = tuple[str, str, dict[str, object]]


def _handle(tmp_path: Path, rows: list[Row]) -> DatabaseTargetHandle:
    path = tmp_path / "assurance.db"
    conn = sqlite3.connect(path)
    conn.executescript(ARCHIVE_ONLY_SCHEMA_SQL + _NODES)
    conn.executemany(
        "INSERT INTO assurance_nodes (node_id, node_type, name, attributes_json) VALUES (?, ?, 'n', ?)",
        [(node_id, node_type, json.dumps(attributes)) for node_id, node_type, attributes in rows],
    )
    conn.commit()
    conn.close()

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(path, isolation_level=None)

    return DatabaseTargetHandle(
        target=UpgradeTarget(
            kind="assurance_sqlcipher",
            stable_id=f"assurance_sqlcipher:{path}",
            display_location=str(path),
            current_version=None,
            credential_requirement="sqlcipher_key",
        ),
        connect=connect,
        inspectable=True,
        path=path,
    )


def _run(handle: DatabaseTargetHandle) -> list[str]:
    """Apply as the orchestration does — only what can be migrated — and return each detail."""
    step = ObligationCitationFormStep()
    view = handle.view()
    uow = handle.begin()
    applied = step.apply(view, uow, [f for f in step.detect(view) if f.auto_migratable])
    uow.commit()
    return [str(outcome.detail) for outcome in applied]


def _attributes(handle: DatabaseTargetHandle, node_id: str) -> dict[str, object]:
    blob = handle.view().query_scalar("SELECT attributes_json FROM assurance_nodes WHERE node_id = ?", (node_id,))
    return dict(json.loads(str(blob)))


def _archive(handle: DatabaseTargetHandle) -> SQLCipherAssuranceArchive:
    assert handle.path is not None
    conn = sqlite3.connect(handle.path)
    conn.row_factory = sqlite3.Row
    return SQLCipherAssuranceArchive(lambda: conn)


class TestAFormerSpellingIsMoved:
    def test_the_wizards_pair_becomes_source_and_provision(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"scheme": "ISO26262", "code": "6-8", "status": "x"})])

        _run(handle)

        assert _attributes(handle, "OBL@1.a.b") == {"source": "ISO26262", "provision": "6-8", "status": "x"}

    def test_the_hand_written_pair_becomes_source_and_provision(self, tmp_path: Path) -> None:
        handle = _handle(
            tmp_path, [("OBL@1.a.b", "obligation", {"framework": "EU AI Act", "clause": "Art. 12", "status": "x"})]
        )

        assert _run(handle) == ["framework -> source, clause -> provision"]
        assert _attributes(handle, "OBL@1.a.b") == {"source": "EU AI Act", "provision": "Art. 12", "status": "x"}
        assert ObligationCitationFormStep().detect(handle.view()) == []

    def test_a_hand_written_pair_on_another_node_type_is_not_touched(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("REQ@1.a.b", "requirement", {"framework": "NIST", "clause": "AC-2"})])

        assert ObligationCitationFormStep().detect(handle.view()) == []

    def test_a_combined_citation_is_split(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"cites": "EU-AI-Act:Art-12"})])

        _run(handle)

        assert _attributes(handle, "OBL@1.a.b") == {"source": "EU-AI-Act", "provision": "Art-12"}

    def test_it_says_what_it_moved(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"scheme": "GDPR", "code": "Art. 5"})])

        assert _run(handle) == ["scheme -> source, code -> provision"]

    def test_a_second_run_finds_nothing(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"scheme": "GDPR", "code": "Art. 5"})])
        _run(handle)

        assert ObligationCitationFormStep().detect(handle.view()) == []
        assert _run(handle) == []

    def test_only_obligations_are_touched(self, tmp_path: Path) -> None:
        """`code` and `scheme` are ordinary words; on another node type they are not a citation."""
        handle = _handle(tmp_path, [("HAZ@1.a.b", "hazard", {"scheme": "STRIDE", "code": "T"})])

        assert ObligationCitationFormStep().detect(handle.view()) == []

    def test_an_obligation_already_current_is_not_a_finding(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"source": "the scheme", "provision": "code 4"})])

        assert ObligationCitationFormStep().detect(handle.view()) == []


class TestWhatCannotBeMovedIsLeftAndReported:
    def test_a_cites_with_no_reading_stays_where_it_is(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"cites": "see the contract"})])

        findings = ObligationCitationFormStep().detect(handle.view())
        _run(handle)

        assert [(f.auto_migratable, f.location) for f in findings] == [(False, "OBL@1.a.b")]
        assert "cites" in findings[0].description
        assert _attributes(handle, "OBL@1.a.b") == {"cites": "see the contract"}

    def test_the_report_does_not_repeat_the_citation(self, tmp_path: Path) -> None:
        """An upgrade report is read outside the store; what an obligation cites is inside it."""
        handle = _handle(tmp_path, [
            ("OBL@1.a.b", "obligation", {"cites": "a confidential contract"}),
            ("OBL@2.a.b", "obligation", {"scheme": "SecretFramework", "code": "Clause-99"}),
        ])

        reported = " ".join(
            f"{f.description} {f.rewrite_summary} {f.manual_instructions}"
            for f in ObligationCitationFormStep().detect(handle.view())
        )

        for confidential in ("confidential contract", "SecretFramework", "Clause-99"):
            assert confidential not in reported


class TestTheRewriteIsOnTheRecord:
    def test_each_rewritten_obligation_has_an_entry_and_the_chain_verifies(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [
            ("OBL@1.a.b", "obligation", {"scheme": "GDPR", "code": "Art. 5"}),
            ("OBL@2.a.b", "obligation", {"cites": "ISO26262:6-8"}),
            ("OBL@3.a.b", "obligation", {"source": "EU AI Act", "provision": "Art. 12"}),
        ])

        _run(handle)

        archive = _archive(handle)
        entries = archive.list_entries()
        assert [(e["operation"], e["node_id"]) for e in entries] == [("UPDATE", "OBL@1.a.b"), ("UPDATE", "OBL@2.a.b")]
        assert archive.verify_chain()

    def test_an_entry_names_the_step_and_the_attributes_never_the_citation(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"scheme": "SecretFramework", "code": "Clause-99"})])

        _run(handle)

        payload = json.loads(str(_archive(handle).list_entries()[0]["payload_json"]))
        assert payload == {
            "updated_fields": ["attributes"],
            "upgrade_step": ObligationCitationFormStep.id,
            "moved_attributes": [["scheme", "source"], ["code", "provision"]],
        }

    def test_entries_join_a_chain_that_already_has_a_head(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"cites": "GDPR:Art. 5"})])
        archive = _archive(handle)
        earlier = archive.append("CREATE", node_id="OBL@1.a.b", payload={"name": "n"})

        _run(handle)

        entries = archive.list_entries()
        assert entries[1]["prev_hash"] == earlier["entry_hash"]
        assert archive.verify_chain()

    def test_a_rolled_back_migration_leaves_neither_the_rewrite_nor_an_entry(self, tmp_path: Path) -> None:
        handle = _handle(tmp_path, [("OBL@1.a.b", "obligation", {"scheme": "GDPR", "code": "Art. 5"})])
        step = ObligationCitationFormStep()
        view = handle.view()
        uow = handle.begin()
        step.apply(view, uow, step.detect(view))
        uow.rollback()

        assert _attributes(handle, "OBL@1.a.b") == {"scheme": "GDPR", "code": "Art. 5"}
        assert _archive(handle).list_entries() == []


def test_the_step_is_registered_for_the_assurance_store() -> None:
    registered = [type(step) for step in build_operational_registry().steps_for("assurance_sqlcipher")]

    assert ObligationCitationFormStep in registered
