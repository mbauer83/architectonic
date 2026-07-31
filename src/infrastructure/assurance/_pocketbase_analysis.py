"""PocketBase REST persistence for the assurance analysis aggregate.

Free functions over an authenticated PocketBase client; the store adapter
delegates its analysis CRUD here to stay focused and within the size budget.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.infrastructure.assurance._analysis_records import apply_analysis_update, new_analysis_record

FilterFn = Callable[..., dict[str, str]]

#: Collection holding the analysis records. Named here rather than spelled at each use site,
#: because filing (`_pocketbase_grouping`) has to reach the same records to unfile them.
ANALYSES_COLLECTION = "assurance_analyses"


def create(
    client: Any,
    url: str,
    name: str,
    method: str,
    architecture_anchor_id: str = "",
    *,
    tlp: str,
    status: str,
) -> str:
    rec = new_analysis_record(name, method, architecture_anchor_id, tlp=tlp, status=status)
    client.post(url, json=rec).raise_for_status()
    return str(rec["analysis_id"])


def get(client: Any, url: str, filter_fn: FilterFn, analysis_id: str) -> dict[str, object] | None:
    resp = client.get(url, params=filter_fn(analysis_id=analysis_id))
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return items[0] if items else None


def list_analyses(
    client: Any,
    url: str,
    filter_fn: FilterFn,
    *,
    method: str | None,
    status: str | None,
) -> list[dict[str, object]]:
    bindings: dict[str, str] = {}
    if method:
        bindings["method"] = method
    if status:
        bindings["status"] = status
    params: dict[str, str | int] = {"perPage": 500}
    params.update(filter_fn(**bindings))
    resp = client.get(url, params=params)
    resp.raise_for_status()
    return resp.json().get("items", [])


def update(client: Any, url: str, record_id: str, attrs: dict[str, object]) -> None:
    payload = apply_analysis_update({}, attrs)
    client.patch(f"{url}/{record_id}", json=payload).raise_for_status()


def delete(client: Any, url: str, record_id: str) -> None:
    client.delete(f"{url}/{record_id}").raise_for_status()


class RestAnalysisStoreMixin:
    """Shared analysis CRUD for PocketBase-style REST assurance stores.

    The host store provides ``_require_unlocked`` (returning the client),
    ``_analysis_url`` and ``_filter``.

    It must also mix in ``RestGroupingStoreMixin``: deleting an analysis has to sweep the
    participation records naming it, and that mixin owns the member collection's URL and filters.
    """

    def _require_unlocked(self) -> Any: ...
    def _analysis_url(self) -> str:
        raise NotImplementedError

    def _filter(self, **bindings: str) -> dict[str, str]:
        raise NotImplementedError

    if TYPE_CHECKING:
        # Implemented by the grouping mixin, which sits *after* this one in the host's MRO — so the
        # declaration is type-checking-only. A runtime stub here would shadow the real
        # implementation and silently sweep nothing, which is the bug this method exists to fix.
        def remove_all_analysis_members_of_analysis(self, analysis_id: str) -> None: ...

    def create_analysis(
        self,
        name: str,
        method: str,
        architecture_anchor_id: str = "",
        *,
        tlp: str = "TLP:WHITE",
        status: str = "draft",
    ) -> str:
        return create(
            self._require_unlocked(), self._analysis_url(),
            name, method, architecture_anchor_id, tlp=tlp, status=status,
        )

    def get_analysis(self, analysis_id: str) -> dict[str, object] | None:
        return get(self._require_unlocked(), self._analysis_url(), self._filter, analysis_id)

    def list_analyses(
        self,
        *,
        method: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        return list_analyses(
            self._require_unlocked(), self._analysis_url(), self._filter,
            method=method, status=status,
        )

    def update_analysis(self, analysis_id: str, **attrs: object) -> None:
        client = self._require_unlocked()
        existing = self.get_analysis(analysis_id)
        if existing is None:
            raise RuntimeError(f"Analysis not found: {analysis_id}")
        update(client, self._analysis_url(), str(existing["id"]), attrs)

    def delete_analysis(self, analysis_id: str) -> None:
        """Delete the analysis record and the participation rows naming it.

        Participation first: interrupted after the analysis record is gone, a retry could not find
        the analysis to know which rows to sweep. This backend has no cascade, so the sweep is the
        whole mechanism. The nodes and their provenance are untouched.
        """
        client = self._require_unlocked()
        existing = self.get_analysis(analysis_id)
        if existing is None:
            return
        self.remove_all_analysis_members_of_analysis(analysis_id)
        delete(client, self._analysis_url(), str(existing["id"]))
