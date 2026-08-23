"""Replacing the assurance graph is an operation the archive has to record.

The archive is the mechanism that discharges the Art. 12 logging obligation, and the constraint the
product holds itself to is stated without exception: *every significant assurance operation must be
recorded in an append-only, tamper-evident archive*. It records twenty-odd of them — a created node,
an edited field, an assigned provenance, a sealed baseline, a shredded record.

It did not record `import`. So a re-seed deleted every node, edge, arch ref, membership and factor
assessment in the store while the chain said nothing had happened. The archive then read *analysis
created, nodes assigned provenance* — and then nothing explaining why none of it is in the store. A
reader reconstructing history from the chain sees effects that vanished with no recorded cause, and
the natural reading of that is tampering.

`audit_log` is deliberately not in `_SECTION_TABLES` or `_DELETE_ORDER`: the chain belongs to the
store rather than to the graph it describes, so an import neither carries one in nor clears the one
that is there. Both halves are asserted below, because "the import is recorded" and "recording it did
not truncate what came before" are separate properties and only the second protects the chain.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

ELEMENT = "APP@1777293133.OYEmP1"


def _store(path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    init_store(path)
    built = SQLCipherAssuranceStore(path)
    built.unlock()
    return built


def _archive(store: Any) -> Any:
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive

    return SQLCipherAssuranceArchive(store.unlocked_connection)


def _populated(path: Path) -> Any:
    """A store holding one of everything an import can destroy."""
    built = _store(path)
    analysis = str(built.create_analysis("Component failures", "FMEA", ELEMENT))
    node = str(built.create_node(
        "failure-mode", "Serves before the clearance check", failure_type="partial-function",
        analysis_id=analysis,
    ))
    built.register_arch_ref(node, ELEMENT, "binds-to")
    built.write_fmea_assessment(
        node_id=node, factor="occurrence", basis_digest="d41d8cd98f00b204e9800998ecf8427e",
        value="unlikely", justification="one report in two years of operation", author="analyst",
    )
    return built


@pytest.fixture()
def bundle(tmp_path: Path) -> dict[str, list[dict[str, object]]]:
    from src.infrastructure.assurance._portability import export_bundle

    source = _populated(tmp_path / "source" / "store.db")
    try:
        return export_bundle(source)
    finally:
        source.lock()


class TestAnImportAppearsInTheChain:
    def test_it_is_recorded(self, bundle: dict[str, Any], tmp_path: Path) -> None:
        from src.infrastructure.assurance._portability import import_bundle

        target = _populated(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True, source="assurance-seed.json")

            recorded = _archive(target).list_entries(operation="IMPORT_BUNDLE")
            assert len(recorded) == 1, "replacing the whole graph left no trace in the archive"
        finally:
            target.lock()

    def test_it_says_what_it_destroyed(self, bundle: dict[str, Any], tmp_path: Path) -> None:
        """The counts are the point. An entry saying only "an import happened" leaves the reader
        with the same unexplained gap, because it does not say the graph was cleared."""
        import json

        from src.infrastructure.assurance._portability import import_bundle

        target = _populated(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True, source="assurance-seed.json")

            entry = _archive(target).list_entries(operation="IMPORT_BUNDLE")[0]
            payload = json.loads(str(entry["payload_json"]))

            assert payload["replace"] is True
            assert payload["source"] == "assurance-seed.json"
            assert payload["cleared"]["assurance_nodes"] == 1
            assert payload["cleared"]["fmea_factor_assessments"] == 1, (
                "an assessment is a human judgement and was deleted unrecorded"
            )
            assert payload["inserted"]["nodes"] == 1
        finally:
            target.lock()

    def test_an_additive_import_says_it_cleared_nothing(
        self, bundle: dict[str, Any], tmp_path: Path
    ) -> None:
        """`replace=False` destroys nothing, and the entry has to distinguish the two — otherwise a
        reader cannot tell a top-up from a wipe."""
        import json

        from src.infrastructure.assurance._portability import import_bundle

        target = _store(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=False, source="assurance-seed.json")

            payload = json.loads(
                str(_archive(target).list_entries(operation="IMPORT_BUNDLE")[0]["payload_json"])
            )

            assert payload["replace"] is False
            assert payload["cleared"] == {}
        finally:
            target.lock()


class TestTheChainSurvivesTheImport:
    def test_what_came_before_is_still_there(self, bundle: dict[str, Any], tmp_path: Path) -> None:
        """A replace clears the graph, not the record of it. If `audit_log` ever joins the delete
        order, this is the test that says why it must not.

        The prior history is appended here rather than left to the fixture's writes: the store's own
        `create_node` does not archive, because appending is the application service's job — so a
        store populated directly has a graph and an empty chain.
        """
        from src.infrastructure.assurance._portability import import_bundle

        target = _populated(tmp_path / "target" / "store.db")
        try:
            _archive(target).append("CREATE", payload={"what": "the history an import must not lose"})
            before = [str(e["operation"]) for e in _archive(target).list_entries(limit=500)]
            assert before, "the fixture must have written history for this to be testing anything"

            import_bundle(target, bundle, replace=True, source="assurance-seed.json")

            after = [str(e["operation"]) for e in _archive(target).list_entries(limit=500)]
            assert after[: len(before)] == before
            assert after[len(before):] == ["IMPORT_BUNDLE"]
        finally:
            target.lock()

    def test_the_hash_chain_still_verifies(self, bundle: dict[str, Any], tmp_path: Path) -> None:
        """The entry is appended through the chained writer, not inserted beside it."""
        from src.infrastructure.assurance._portability import import_bundle

        target = _populated(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True, source="assurance-seed.json")

            assert _archive(target).verify_chain()
        finally:
            target.lock()

    def test_the_bundle_cannot_carry_a_chain_into_the_store(
        self, bundle: dict[str, Any], tmp_path: Path
    ) -> None:
        """An imported chain would be one store's hashes presented as another's. The export does not
        emit the section, and an import offered one anyway ignores it."""
        from src.infrastructure.assurance._portability import import_bundle

        assert "audit_log" not in bundle
        target = _store(tmp_path / "target" / "store.db")
        try:
            import_bundle(
                target,
                {**bundle, "audit_log": [{"seq": 1, "operation": "FABRICATED", "entry_hash": "x"}]},
                replace=True,
            )

            operations = [str(e["operation"]) for e in _archive(target).list_entries(limit=500)]
            assert "FABRICATED" not in operations
        finally:
            target.lock()
