"""PocketBase REST persistence for analysis filing and participation.

Sits beside `_pocketbase_analysis` because unfiling on group deletion has to write the analysis
collection, and naming that collaborator directly is what keeps the dependency real rather than a
property of the host store's base-class order. Record shape and ordering are shared with the other
backends in `_grouping_records`.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.assurance._grouping_records import (
    GROUPS_COLLECTION,
    MEMBERS_COLLECTION,
    as_group_record,
    new_group_record,
    new_member_record,
    sorted_by_added,
    sorted_by_name,
)
from src.infrastructure.assurance._pocketbase_analysis import (
    ANALYSES_COLLECTION,
)
from src.infrastructure.assurance._pocketbase_analysis import (
    list_raw as list_analysis_records_raw,
)
from src.infrastructure.assurance._pocketbase_analysis import (
    update as update_analysis_record,
)


class RestGroupingStoreMixin:
    """Groups and memberships in two PocketBase collections.

    Expects the host store to expose `_require_unlocked()` returning an HTTP client and
    `_filter(**bindings)` building a parameterized filter. The filter helper is reused rather
    than reimplemented so this cannot become a second, injectable way of querying the server.
    """

    def _require_unlocked(self) -> Any:
        raise NotImplementedError("provided by the host store")

    def _filter(self, **bindings: str) -> dict[str, str]:
        raise NotImplementedError("provided by the host store")

    def _group_url(self) -> str:
        return f"/api/collections/{GROUPS_COLLECTION}/records"

    def _member_url(self) -> str:
        return f"/api/collections/{MEMBERS_COLLECTION}/records"

    def _analyses_url(self) -> str:
        return f"/api/collections/{ANALYSES_COLLECTION}/records"

    def _items(self, url: str, **bindings: str) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"perPage": 500}
        params.update(self._filter(**bindings))
        resp = self._require_unlocked().get(url, params=params)
        resp.raise_for_status()
        items: list[dict[str, Any]] = resp.json().get("items", [])
        return items

    # ── Groups ────────────────────────────────────────────────────────────────

    def create_group(self, name: str, description: str = "") -> str:
        record = new_group_record(name, description)
        self._require_unlocked().post(self._group_url(), json=record).raise_for_status()
        return str(record["group_id"])

    def get_group(self, group_id: str) -> dict[str, object] | None:
        items = self._items(self._group_url(), group_id=group_id)
        return as_group_record(items[0]) if items else None

    def list_groups(self) -> list[dict[str, object]]:
        # Projected on the way out, not in `_items`: `delete_group` below addresses each group at
        # PocketBase's own row id, which the canonical record deliberately does not carry.
        return [as_group_record(record) for record in sorted_by_name(self._items(self._group_url()))]

    def delete_group(self, group_id: str) -> None:
        """Remove the group and unfile its analyses. Their content is untouched."""
        client = self._require_unlocked()
        # Unprojected, because unfiling PATCHes each analysis at its PocketBase row id.
        filed = list_analysis_records_raw(
            client, self._analyses_url(), self._filter, method=None, status=None
        )
        for analysis in filed:
            if str(analysis.get("group_id") or "") == group_id:
                update_analysis_record(
                    client, self._analyses_url(), str(analysis["id"]), {"group_id": None}
                )
        for item in self._items(self._group_url(), group_id=group_id):
            client.delete(f"{self._group_url()}/{item['id']}").raise_for_status()

    # ── Participation ─────────────────────────────────────────────────────────

    def add_analysis_member(self, analysis_id: str, node_id: str) -> None:
        """Idempotent by contract, so an existing pair is left as it is rather than duplicated."""
        client = self._require_unlocked()
        if self._items(self._member_url(), analysis_id=analysis_id, node_id=node_id):
            return
        client.post(
            self._member_url(), json=new_member_record(analysis_id, node_id)
        ).raise_for_status()

    def remove_analysis_member(self, analysis_id: str, node_id: str) -> None:
        client = self._require_unlocked()
        for item in self._items(self._member_url(), analysis_id=analysis_id, node_id=node_id):
            client.delete(f"{self._member_url()}/{item['id']}").raise_for_status()

    def remove_all_analysis_members_of_analysis(self, analysis_id: str) -> None:
        """Drop every participation naming this analysis, for use when the analysis is deleted.

        The counterpart of the node-side sweep below. Without it an analysis that only *borrowed*
        nodes leaves one orphan row per borrowed node — and this backend has no cascade at all, so
        the sweep is the whole mechanism. The nodes and their provenance are untouched.
        """
        client = self._require_unlocked()
        for item in self._items(self._member_url(), analysis_id=analysis_id):
            client.delete(f"{self._member_url()}/{item['id']}").raise_for_status()

    def remove_all_analysis_members_of_node(self, node_id: str) -> None:
        """Drop every membership naming this node, for use when the node itself is deleted.

        The REST backend has no cascade to fall back on, so this is the only thing standing
        between a deleted node and memberships that outlive it.
        """
        client = self._require_unlocked()
        for item in self._items(self._member_url(), node_id=node_id):
            client.delete(f"{self._member_url()}/{item['id']}").raise_for_status()

    def list_analysis_members(self, analysis_id: str) -> list[str]:
        return sorted_by_added(self._items(self._member_url(), analysis_id=analysis_id))

    def list_participating_analyses(self, node_id: str) -> list[str]:
        records = sorted(
            self._items(self._member_url(), node_id=node_id),
            key=lambda record: str(record.get("added_at", "")),
        )
        return [str(record["analysis_id"]) for record in records]
