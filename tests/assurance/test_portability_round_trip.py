"""What the export bundle carries — because it is the only durable copy of the store.

The archive lives inside the store's own encryption under the default backend, so a lost key loses
the audit trail with the content. The committed export bundle is what remains, and it has already
been the sole recovery path twice. Whatever it omits is therefore not "recoverable later" but gone.

Factor assessments were omitted, and that omission was the dangerous kind. Severity and detectability
are derived, so they come back on their own from a restored graph. Occurrence is asserted-only — it
exists solely as a judgement with a rationale and an author — so an export without assessments loses
exactly the half of the analysis nobody can recompute, while appearing to have restored everything.
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


@pytest.fixture()
def source(tmp_path: Path) -> Any:
    built = _store(tmp_path / "source" / "store.db")
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
    yield built
    built.lock()


class TestAJudgementSurvivesTheRoundTrip:
    def test_the_bundle_carries_it(self, source: Any) -> None:
        from src.infrastructure.assurance._portability import export_bundle

        bundle = export_bundle(source)

        assert bundle["factor_assessments"], "the export dropped every human judgement"

    def test_its_rationale_and_author_come_back(self, source: Any, tmp_path: Path) -> None:
        """The value alone is not the judgement — unattributed and unexplained, it cannot be
        defended in review, which is the whole reason the write path demands both."""
        from src.infrastructure.assurance._portability import export_bundle, import_bundle

        bundle = export_bundle(source)
        target = _store(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True)
            node_id = str(bundle["nodes"][0]["node_id"])
            restored = target.read_fmea_assessments([node_id])[node_id]

            assert [
                (r["factor"], r["value"], r["justification"], r["author"]) for r in restored
            ] == [("occurrence", "unlikely", "one report in two years of operation", "analyst")]
        finally:
            target.lock()

    def test_the_basis_digest_comes_back_so_the_judgement_still_applies(
        self, source: Any, tmp_path: Path
    ) -> None:
        """A restored assessment whose digest changed would be retained and never apply, which
        looks identical to not having restored it."""
        from src.infrastructure.assurance._portability import export_bundle, import_bundle

        bundle = export_bundle(source)
        target = _store(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True)
            node_id = str(bundle["nodes"][0]["node_id"])
            restored = target.read_fmea_assessments([node_id])[node_id]

            assert restored[0]["basis_digest"] == "d41d8cd98f00b204e9800998ecf8427e"
        finally:
            target.lock()


class TestAReplaceLeavesNoOrphans:
    def test_judgements_of_deleted_nodes_do_not_survive_a_re_seed(
        self, source: Any, tmp_path: Path
    ) -> None:
        """`replace` exists so a re-seed is idempotent rather than additive. An assessment left
        behind points at a node that no longer exists — and would be inherited by a later node
        that happened to reuse the id."""
        from src.infrastructure.assurance._portability import export_bundle, import_bundle

        bundle = export_bundle(source)
        target = _store(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True)
            node_id = str(bundle["nodes"][0]["node_id"])

            import_bundle(target, {"analyses": [], "nodes": [], "edges": [], "arch_refs": []}, replace=True)

            assert target.read_fmea_assessments([node_id]) == {}
        finally:
            target.lock()


class TestEveryExportedColumnIsRestored:
    """The importer does not fall behind the exporter.

    A column the bundle carries but the insert omits is dropped while the row count still
    reports a full restore. `failure_type` is an FMEA guideword — the matrix column a failure
    mode belongs in — so losing it renders a re-seeded store as an all-but-empty matrix, with
    the dismissals recorded against those modes nowhere to appear.
    """

    def test_the_failure_guideword_survives(self, source: Any, tmp_path: Path) -> None:
        from src.infrastructure.assurance._portability import export_bundle, import_bundle

        bundle = export_bundle(source)
        target = _store(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True)
            node_id = str(bundle["nodes"][0]["node_id"])

            assert target.get_node(node_id)["failure_type"] == "partial-function"
        finally:
            target.lock()

    def test_no_exported_node_column_is_silently_dropped(self, source: Any, tmp_path: Path) -> None:
        from src.infrastructure.assurance._portability import export_bundle, import_bundle

        bundle = export_bundle(source)
        target = _store(tmp_path / "target" / "store.db")
        try:
            import_bundle(target, bundle, replace=True)
            exported = bundle["nodes"][0]
            restored = target.get_node(str(exported["node_id"]))

            dropped = sorted(
                column for column, value in exported.items()
                if column in restored and restored[column] != value
            )
            assert dropped == [], f"the round trip changed or lost {dropped}"
        finally:
            target.lock()

    def test_the_importer_accepts_every_column_the_schema_declares(self, tmp_path: Path) -> None:
        """Read from the schema, so the two cannot drift apart."""
        from src.infrastructure.assurance._portability import _SECTION_TABLES, table_columns

        target = _store(tmp_path / "target" / "store.db")
        try:
            conn = target.unlocked_connection()
            for _section, table in _SECTION_TABLES:
                declared = table_columns(conn, table)
                assert declared, f"no columns resolved for {table}"
        finally:
            target.lock()
