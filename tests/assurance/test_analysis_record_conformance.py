"""Every assurance record has one shape and one meaning, whichever backend stored it.

It had three. SQLCipher's ``SELECT *`` returned nine columns. A file-backed record written before it
had ever been filed had eight — ``group_id`` was simply absent, because ``new_analysis_record`` did
not write it. PocketBase returned its own collection metadata alongside the eight: ``id``,
``collectionId``, ``collectionName``, ``created``, ``updated``.

Nothing failed, because nothing compared them. The consequence surfaced one layer up: no closed
response contract can be published over a record whose key set depends on which store the deployment
is configured with, and a contract closed against one backend answers 500 on another. So the
projection belongs at the store boundary, and this is the test that holds every backend to it.

``id`` is dropped deliberately. It addresses a row inside PocketBase and means nothing outside it —
which is why the adapter keeps unprojected reads for its own ``PATCH``/``DELETE`` URLs and exposes
neither.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.assurance._analysis_records import (
    ANALYSIS_RECORD_FIELDS,
    as_analysis_record,
    new_analysis_record,
)
from src.infrastructure.assurance._edge_records import (
    ARCH_REF_RECORD_FIELDS,
    EDGE_RECORD_FIELDS,
)
from src.infrastructure.assurance._grouping_records import GROUP_RECORD_FIELDS
from src.infrastructure.assurance._node_records import NODE_RECORD_FIELDS
from tests.support.assurance_backends import ASSURANCE_BACKENDS, BACKEND_NAMES


@pytest.fixture(params=BACKEND_NAMES, ids=BACKEND_NAMES)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    yield from ASSURANCE_BACKENDS[request.param](tmp_path)


class TestEveryBackendReturnsTheCanonicalRecord:
    def test_a_freshly_created_analysis_reads_back_with_exactly_the_canonical_fields(
        self, store: Any
    ) -> None:
        analysis_id = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))

        record = store.get_analysis(analysis_id)

        assert record is not None
        assert set(record) == set(ANALYSIS_RECORD_FIELDS)

    def test_the_list_agrees_with_the_detail_read(self, store: Any) -> None:
        """Two code paths per backend, and a projection applied to one of them is the shape of defect
        that reaches a client only when they scroll a list rather than open a record."""
        analysis_id = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))

        listed = [row for row in store.list_analyses() if row["analysis_id"] == analysis_id]

        assert len(listed) == 1
        assert set(listed[0]) == set(ANALYSIS_RECORD_FIELDS)
        assert listed[0] == store.get_analysis(analysis_id)

    def test_an_unfiled_analysis_reports_no_group_rather_than_omitting_the_field(
        self, store: Any
    ) -> None:
        """Absent and null are different answers to "which group is this in?", and only one of them
        is representable in a closed contract."""
        analysis_id = str(store.create_analysis("Valves", "GRC", tlp="TLP:WHITE"))

        record = store.get_analysis(analysis_id)

        assert record is not None
        assert "group_id" in record
        assert record["group_id"] is None

    def test_the_backend_s_own_row_identity_never_leaves_the_backend(self, store: Any) -> None:
        """PocketBase's ``id`` is its collection's primary key. Passed on, it invites a caller to
        treat one store's key as this system's identity — and the analysis already has one."""
        analysis_id = str(store.create_analysis("Seals", "STPA", tlp="TLP:WHITE"))

        record = store.get_analysis(analysis_id)

        assert record is not None
        assert "id" not in record
        assert record["analysis_id"] == analysis_id

    def test_filing_an_analysis_shows_up_as_a_group(self, store: Any) -> None:
        """The field is not merely present-and-null: it carries the filing, in every backend."""
        analysis_id = str(store.create_analysis("Housing", "STPA", tlp="TLP:WHITE"))
        group_id = str(store.create_group("Mechanical"))

        store.update_analysis(analysis_id, group_id=group_id)

        record = store.get_analysis(analysis_id)
        assert record is not None
        assert record["group_id"] == group_id


class TestEveryBackendReturnsTheCanonicalGroupRecord:
    """A group had the same defect, minus the missing field: five columns from SQLCipher and the file
    stores, those five plus PocketBase's collection metadata from PocketBase."""

    def test_a_freshly_created_group_reads_back_with_exactly_the_canonical_fields(
        self, store: Any
    ) -> None:
        group_id = str(store.create_group("Mechanical", "Brakes, pumps, valves"))

        record = store.get_group(group_id)

        assert record is not None
        assert set(record) == set(GROUP_RECORD_FIELDS)
        assert record["group_id"] == group_id
        assert record["description"] == "Brakes, pumps, valves"

    def test_the_group_list_agrees_with_the_detail_read(self, store: Any) -> None:
        group_id = str(store.create_group("Electrical"))

        listed = [row for row in store.list_groups() if row["group_id"] == group_id]

        assert len(listed) == 1
        assert listed[0] == store.get_group(group_id)

    def test_deleting_a_group_still_unfiles_its_analyses(self, store: Any) -> None:
        """The regression for the projection itself. PocketBase addresses each group and each analysis
        by its own row id when unfiling, so a projection applied one layer too early would leave the
        analyses filed under a group that no longer exists."""
        group_id = str(store.create_group("Hydraulics"))
        analysis_id = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
        store.update_analysis(analysis_id, group_id=group_id)

        store.delete_group(group_id)

        assert store.get_group(group_id) is None
        surviving = store.get_analysis(analysis_id)
        assert surviving is not None, "deleting a folder must not delete what is filed in it"
        assert surviving["group_id"] is None


class TestEveryBackendReturnsTheCanonicalNodeRecord:
    """The record that matters most: nearly every read on this surface embeds a node.

    Nineteen columns from SQLCipher, seventeen from the file stores, seventeen plus collection
    metadata from PocketBase — and the frontend's decoder was wrong in both directions at once,
    requiring the one field only SQLCipher sends and omitting two every store writes.
    """

    def test_a_freshly_created_node_reads_back_with_exactly_the_canonical_fields(
        self, store: Any
    ) -> None:
        analysis_id = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        node_id = str(store.create_node("hazard", "Uncommanded braking", analysis_id=analysis_id))

        record = store.get_node(node_id)

        assert record is not None
        assert set(record) == set(NODE_RECORD_FIELDS)
        assert record["node_id"] == node_id
        assert record["analysis_id"] == analysis_id

    def test_the_node_list_and_the_search_agree_with_the_detail_read(self, store: Any) -> None:
        """Three read paths per backend. A projection applied to one of them is the shape of defect
        that reaches a client only when they scroll, or only when they search."""
        analysis_id = str(store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
        node_id = str(store.create_node("failure-mode", "Seal weeps", analysis_id=analysis_id))
        detail = store.get_node(node_id)

        listed = [row for row in store.list_nodes() if row["node_id"] == node_id]
        found = [row for row in store.search_nodes("Seal weeps") if row["node_id"] == node_id]

        assert listed == [detail]
        assert found == [detail]

    def test_an_attribution_this_system_does_not_record_is_not_published(self, store: Any) -> None:
        """``created_by`` is a SQLCipher column with an empty default that nothing writes. Sending it
        would document an author the store never captured — and only one backend would send it."""
        analysis_id = str(store.create_analysis("Valves", "GRC", tlp="TLP:WHITE"))
        node_id = str(store.create_node("risk", "Quarterly review", analysis_id=analysis_id))

        record = store.get_node(node_id)

        assert record is not None
        assert "created_by" not in record
        assert "id" not in record

    def test_the_discriminated_fields_are_present_and_null_rather_than_absent(
        self, store: Any
    ) -> None:
        """A hazard has no ``uca_type``; the field is still there. Absent and null are different
        answers, and a closed contract can only represent one of them."""
        analysis_id = str(store.create_analysis("Seals", "STPA", tlp="TLP:WHITE"))
        node_id = str(store.create_node("hazard", "Loss of seal", analysis_id=analysis_id))

        record = store.get_node(node_id)

        assert record is not None
        for field in ("uca_type", "failure_type", "mode", "concern_class", "node_role"):
            assert field in record, field
            assert record[field] is None, field


class TestEveryBackendReturnsTheCanonicalRelationRecords:
    """A node's two relations: the edges between nodes, and the references out to architecture.

    Both are read by the routes that read a node, so a closed contract for a node detail depends on
    all three records agreeing across the backends.
    """

    def _two_nodes(self, store: Any) -> tuple[str, str]:
        analysis_id = str(store.create_analysis("Brakes", "STPA", tlp="TLP:WHITE"))
        hazard = str(store.create_node("hazard", "Uncommanded braking", analysis_id=analysis_id))
        loss = str(store.create_node("loss", "Occupant injury", analysis_id=analysis_id))
        return hazard, loss

    def test_an_edge_reads_back_with_exactly_the_canonical_fields(self, store: Any) -> None:
        hazard, loss = self._two_nodes(store)
        edge_id = str(store.add_edge(hazard, loss, "leads-to"))

        listed = [edge for edge in store.list_edges() if edge["edge_id"] == edge_id]

        assert len(listed) == 1
        assert set(listed[0]) == set(EDGE_RECORD_FIELDS)
        assert listed[0]["source_id"] == hazard
        assert listed[0]["target_id"] == loss

    def test_the_filtered_edge_reads_agree_with_the_unfiltered_one(self, store: Any) -> None:
        """Three filters over one query per backend, and a projection on the general path only is the
        defect that appears when a reader opens a node rather than the edge list."""
        hazard, loss = self._two_nodes(store)
        edge_id = str(store.add_edge(hazard, loss, "leads-to"))
        whole = [edge for edge in store.list_edges() if edge["edge_id"] == edge_id]

        assert store.list_edges(source_id=hazard) == whole
        assert store.list_edges(target_id=loss) == whole
        assert store.list_edges(conn_type="leads-to") == whole

    def test_an_unresolved_architecture_reference_reads_as_null_not_empty(self, store: Any) -> None:
        """PocketBase cannot store null in a text field, so it wrote ``""`` for "not yet resolved"
        while every other store wrote ``None`` — two answers to the same question about the same
        reference."""
        hazard, _loss = self._two_nodes(store)
        store.register_arch_ref(hazard, "APP@1.aaaa.brake-controller", "mitigates")

        refs = store.list_arch_refs(assurance_node_id=hazard)

        assert len(refs) == 1
        assert set(refs[0]) == set(ARCH_REF_RECORD_FIELDS)
        assert refs[0]["resolved_at"] is None

    def test_resolving_a_reference_records_when(self, store: Any) -> None:
        """The field is not merely present-and-null: it carries the resolution, in every backend —
        and on PocketBase the write is addressed by a row id the canonical record does not carry."""
        hazard, _loss = self._two_nodes(store)
        store.register_arch_ref(hazard, "APP@1.aaaa.brake-controller", "mitigates")

        store.mark_arch_ref_resolved(hazard, "APP@1.aaaa.brake-controller", "mitigates")

        refs = store.list_arch_refs(assurance_node_id=hazard)
        assert len(refs) == 1
        assert refs[0]["resolved_at"] is not None


class TestTheProjectionItself:
    def test_a_new_record_already_has_the_canonical_field_set(self) -> None:
        """Rather than acquiring ``group_id`` the first time it happens to be filed."""
        assert set(new_analysis_record("Brakes", "STPA")) == set(ANALYSIS_RECORD_FIELDS)

    def test_a_record_stored_before_group_id_existed_still_projects(self) -> None:
        """The store is not rewritten to add the field — opening an older store is non-destructive,
        so the projection has to tolerate its absence rather than the store being migrated."""
        legacy = {
            field: "x" for field in ANALYSIS_RECORD_FIELDS if field != "group_id"
        }

        assert as_analysis_record(legacy)["group_id"] is None

    def test_a_record_missing_a_required_field_is_refused_rather_than_filled_in(self) -> None:
        """Defaulting a missing ``method`` would publish an analysis whose method this code invented."""
        incomplete = {field: "x" for field in ANALYSIS_RECORD_FIELDS if field != "method"}

        with pytest.raises(ValueError, match="method"):
            as_analysis_record(incomplete)
