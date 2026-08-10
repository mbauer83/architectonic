"""The three assurance reads that need more than the store: the archive, and a signal snapshot.

`assurance_cast_complete`, `assurance_list_bom_components` and `assurance_list_vulnerabilities` were
the last MCP tools with no test naming them. Each reads a collaborator the store-only harness in
`test_assurance_read_tools_answer_about_real_content.py` does not provide, so this module builds the
bundle the way `store_factory` does — the archive and the snapshot store are both constructed from the
opened SQLCipher store's own connection factory — rather than stubbing a lookalike.

Going through `store_factory.get_assurance_bundle` would read the OS credential store to decide the
activation gate. That is deliberately avoided: these tests are about what the tools answer, not about
this machine's keychain.

Counts are exact because the store is this module's own.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read

ANCHOR = "APC@1000000001.aaaa.payments-api"
OTHER_ANCHOR = "APC@1000000002.bbbb.reporting-api"
#: The store canonicalises an entity id to `PREFIX@epoch.random`, and that is the form every read
#: reports back regardless of which form it was asked with.
CANONICAL_ANCHOR = "APC@1000000001.aaaa"
CANONICAL_OTHER = "APC@1000000002.bbbb"


@pytest.fixture()
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Store, archive and snapshot store over one SQLCipher database, as the factory wires them."""
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store
    from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext

    db_path = tmp_path / "collaborators.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    conn_factory = store._thread_conn_or_none  # noqa: SLF001
    archive = SQLCipherAssuranceArchive(conn_factory)
    snapshots = SQLCipherSnapshotStore(conn_factory)

    monkeypatch.setattr(
        AssuranceContext,
        "_bundle",
        lambda _self: SimpleNamespace(store=store, archive=archive, snapshot_store=snapshots),
    )
    yield SimpleNamespace(store=store, archive=archive, snapshots=snapshots)
    store.lock()


def _call(tool: str, **arguments: object) -> dict[str, Any]:
    _unstructured, structured = asyncio.run(mcp_assurance_read.call_tool(tool, arguments))
    return structured


def _ingest(
    snapshots: Any,
    snapshot_id: str,
    *,
    anchor: str,
    component: str = "urllib3",
    external_ids: tuple[str, ...] = ("CVE-2026-0001",),
    band: str = "high",
) -> None:
    """One active snapshot for `anchor`, carrying one component and one finding against it."""
    snapshots.create_staging_snapshot(
        snapshot_id=snapshot_id,
        anchor_entity_id=anchor,
        request_id=f"req-{snapshot_id}",
        request_payload_digest=f"digest-{snapshot_id}",
    )
    snapshots.populate_snapshot(
        snapshot_id,
        components=[{
            "component_id": component, "name": component,
            "purl": f"pkg:pypi/{component}@1", "version": "1", "directness": "direct",
        }],
        findings=[{
            "component_id": component, "external_ids": list(external_ids),
            "severity_band": band, "cvss_score": 8.1,
        }],
    )
    snapshots.complete_snapshot(snapshot_id)
    snapshots.activate_snapshot(snapshot_id)


class TestListBomComponents:
    def test_it_lists_the_components_of_the_anchor_it_was_asked_about(self, bundle: Any) -> None:
        _ingest(bundle.snapshots, "SNAP@1", anchor=ANCHOR, component="urllib3")

        answer = _call("assurance_list_bom_components", anchor_entity_id=ANCHOR)

        assert answer["count"] == 1
        assert {str(c["name"]) for c in answer["components"]} == {"urllib3"}

    def test_it_does_not_answer_with_another_anchor_s_components(self, bundle: Any) -> None:
        """`anchor_entity_id` is the whole input; a read ignoring it would return everything."""
        _ingest(bundle.snapshots, "SNAP@1", anchor=ANCHOR, component="urllib3")
        _ingest(bundle.snapshots, "SNAP@2", anchor=OTHER_ANCHOR, component="requests")

        assert {str(c["name"]) for c in _call(
            "assurance_list_bom_components", anchor_entity_id=ANCHOR)["components"]} == {"urllib3"}
        assert {str(c["name"]) for c in _call(
            "assurance_list_bom_components", anchor_entity_id=OTHER_ANCHOR)["components"]} == {"requests"}

    def test_an_anchor_with_no_snapshot_answers_empty(self, bundle: Any) -> None:
        answer = _call("assurance_list_bom_components", anchor_entity_id=ANCHOR)
        assert answer["count"] == 0
        assert answer["components"] == []


def _anchors(answer: dict[str, Any]) -> set[str]:
    return {str(f["assessed_entity_id"]) for f in answer["findings"]}


def _components(answer: dict[str, Any]) -> set[str]:
    return {str(f["component_name"]) for f in answer["findings"]}


class TestListVulnerabilities:
    def test_it_reports_the_finding_against_the_assessed_entity(self, bundle: Any) -> None:
        # A finding names the vulnerability by its *canonical* id, not by the external id it was
        # ingested under — aliases resolve to one canonical vulnerability, so the row carries that.
        _ingest(bundle.snapshots, "SNAP@1", anchor=ANCHOR)

        answer = _call("assurance_list_vulnerabilities", assessed_entity_id=ANCHOR)

        assert answer["count"] == 1
        assert _anchors(answer) == {CANONICAL_ANCHOR}
        assert _components(answer) == {"urllib3"}
        assert str(answer["findings"][0]["canonical_vulnerability_id"]).startswith("VID@")

    def test_scoping_to_one_entity_excludes_the_other(self, bundle: Any) -> None:
        _ingest(bundle.snapshots, "SNAP@1", anchor=ANCHOR)
        _ingest(bundle.snapshots, "SNAP@2", anchor=OTHER_ANCHOR, component="requests")

        assert _anchors(_call(
            "assurance_list_vulnerabilities", assessed_entity_id=ANCHOR)) == {CANONICAL_ANCHOR}
        assert _anchors(_call(
            "assurance_list_vulnerabilities", assessed_entity_id=OTHER_ANCHOR)) == {CANONICAL_OTHER}

    def test_unscoped_it_reports_across_every_assessed_entity(self, bundle: Any) -> None:
        # The default is deliberately store-wide: a caller with no entity in mind is asking what is
        # outstanding anywhere.
        _ingest(bundle.snapshots, "SNAP@1", anchor=ANCHOR)
        _ingest(bundle.snapshots, "SNAP@2", anchor=OTHER_ANCHOR, component="requests")

        everything = _call("assurance_list_vulnerabilities")

        assert everything["count"] == 2
        assert _anchors(everything) == {CANONICAL_ANCHOR, CANONICAL_OTHER}

    def test_the_scoped_and_unscoped_reads_agree_on_the_entity_id(self, bundle: Any) -> None:
        """The defect this pins: the scoped read echoed the caller's id, the unscoped one reported
        the stored one, so joining the two result sets on `assessed_entity_id` matched nothing.

        Asked with the *slugged* form on purpose — that is the form a caller holds from the
        architecture repository, and the form that used to come back unchanged.
        """
        _ingest(bundle.snapshots, "SNAP@1", anchor=ANCHOR)

        scoped = _anchors(_call("assurance_list_vulnerabilities", assessed_entity_id=ANCHOR))
        unscoped = _anchors(_call("assurance_list_vulnerabilities"))

        assert scoped == unscoped == {CANONICAL_ANCHOR}

    def test_the_purl_filter_selects_rather_than_being_ignored(self, bundle: Any) -> None:
        _ingest(bundle.snapshots, "SNAP@1", anchor=ANCHOR, component="urllib3")
        _ingest(bundle.snapshots, "SNAP@2", anchor=OTHER_ANCHOR, component="requests")

        answer = _call("assurance_list_vulnerabilities", purl="pkg:pypi/urllib3@1")

        assert _components(answer) == {"urllib3"}


class TestCastComplete:
    def test_an_incident_with_no_sealed_baseline_fails_the_profile(self, bundle: Any) -> None:
        """The check that needs the archive: CAST cannot be complete over unsealed evidence."""
        analysis_id = bundle.store.create_analysis("Outage review", "cast")
        bundle.store.create_node("incident", "Payment outage", analysis_id=analysis_id)

        answer = _call("assurance_cast_complete")

        assert answer["passed"] is False
        assert "checks" in answer

    def test_it_reads_the_archive_rather_than_assuming_nothing_is_sealed(self, bundle: Any) -> None:
        """A profile that never consulted the archive would answer identically either way.

        Sealing a baseline is the one thing that can change the incident check's verdict, so the two
        answers must differ. Without this, `run_cast_complete` could ignore its `archive` argument
        and every other assertion here would still pass.
        """
        analysis_id = bundle.store.create_analysis("Outage review", "cast")
        bundle.store.create_node("incident", "Payment outage", analysis_id=analysis_id)
        before = _call("assurance_cast_complete")

        # A baseline seals the audit log's head, so there has to be a head to seal.
        bundle.archive.append("REVIEW", payload={"note": "incident triaged"})
        bundle.archive.seal_baseline(analysis_id=analysis_id)
        after = _call("assurance_cast_complete")

        assert before != after

    def test_an_empty_store_has_no_incident_to_fault(self, bundle: Any) -> None:
        answer = _call("assurance_cast_complete")
        assert "checks" in answer
        assert "passed" in answer


def test_all_three_refuse_a_locked_store(bundle: Any) -> None:
    bundle.store.lock()
    for tool, arguments in (
        ("assurance_cast_complete", {}),
        ("assurance_list_bom_components", {"anchor_entity_id": ANCHOR}),
        ("assurance_list_vulnerabilities", {}),
    ):
        answer = _call(tool, **arguments)
        assert "error" in answer, tool
        assert str(answer["error"]["code"]) == "assurance_store_locked", tool
