"""Application-layer exposure policy for the confidential assurance store.

AssuranceExposurePolicy is the single filter applied to every assurance read.
HTTP and MCP adapters call this policy and translate its typed outcomes into
their transport-specific responses. Infrastructure stores do not decide exposure.

Outcome types (sealed):
  Visible(value, scope)  — content within ceiling; caller may return it
  Locked                 — store not unlocked; HTTP 423, MCP locked envelope
  NotFound               — absent OR above-ceiling; HTTP 404, MCP not_found
  ForbiddenWrite         — write TLP exceeds ceiling; HTTP 403 (writes only)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_TLP_ORDER: dict[str, int] = {
    "TLP:WHITE": 0,
    "TLP:GREEN": 1,
    "TLP:AMBER": 2,
    "TLP:RED": 3,
}


def _tlp_level(tlp: str) -> int:
    return _TLP_ORDER.get(str(tlp).upper(), 0)


def is_above_ceiling(tlp: str, ceiling: str) -> bool:
    """Return True when tlp is more sensitive than ceiling."""
    return _tlp_level(tlp) > _tlp_level(ceiling)


@dataclass(frozen=True)
class PolicyScope:
    """Attached to Visible; never discloses withheld cardinality to callers."""

    ceiling: str
    visibility_limited: bool  # True when ceiling < TLP:RED


@dataclass(frozen=True)
class Visible:
    """Content is within ceiling and may be returned."""

    value: Any
    scope: PolicyScope


@dataclass(frozen=True)
class Locked:
    """Store not unlocked; nothing returned."""


@dataclass(frozen=True)
class NotFound:
    """Absent OR above-ceiling — intentionally indistinguishable."""


@dataclass(frozen=True)
class ForbiddenWrite:
    """Write whose TLP exceeds ceiling (read surfaces must never emit this)."""


class AssuranceExposurePolicy:
    """Stateless per-request filter; ceiling read once at construction.

    Usage::

        policy = AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())
        if locked := policy.check_locked():
            return _423(locked)            # HTTP or MCP locked envelope
        nodes, withheld = policy.filter_nodes(store.list_nodes())
        ...
    """

    def __init__(self, ceiling: str, is_unlocked: bool) -> None:
        self._ceiling = ceiling
        self._unlocked = is_unlocked

    # ── Store gate ────────────────────────────────────────────────────────────

    def check_locked(self) -> Locked | None:
        return Locked() if not self._unlocked else None

    def scope(self) -> PolicyScope:
        return PolicyScope(
            ceiling=self._ceiling,
            visibility_limited=_tlp_level(self._ceiling) < _tlp_level("TLP:RED"),
        )

    # ── Collection filters ────────────────────────────────────────────────────

    def filter_nodes(
        self,
        nodes: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (visible_nodes, withheld_count).

        Withheld count is safe to report (reveals no classified content).
        Nodes without a tlp key default to TLP:WHITE.
        """
        visible: list[dict[str, Any]] = []
        withheld = 0
        for node in nodes:
            if is_above_ceiling(str(node.get("tlp", "TLP:WHITE")), self._ceiling):
                withheld += 1
            else:
                visible.append(node)
        return visible, withheld

    def filter_edges(
        self,
        edges: list[dict[str, Any]],
        visible_node_ids: frozenset[str],
    ) -> list[dict[str, Any]]:
        """Return edges where BOTH source and target are in the visible set.

        An edge with a hidden endpoint reveals that node's existence and
        participation — both are withheld silently.
        """
        return [
            e for e in edges
            if str(e.get("source_id", "")) in visible_node_ids
            and str(e.get("target_id", "")) in visible_node_ids
        ]

    def filter_security_records(
        self,
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """Filter BOM components and vulnerabilities by TLP ceiling.

        Security records default to TLP:AMBER when tlp is absent.
        """
        visible: list[dict[str, Any]] = []
        withheld = 0
        for rec in records:
            if is_above_ceiling(str(rec.get("tlp", "TLP:AMBER")), self._ceiling):
                withheld += 1
            else:
                visible.append(rec)
        return visible, withheld

    def filter_analyses(
        self,
        analyses: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (visible_analyses, withheld_count). Analyses default to TLP:WHITE."""
        visible: list[dict[str, Any]] = []
        withheld = 0
        for analysis in analyses:
            if is_above_ceiling(str(analysis.get("tlp", "TLP:WHITE")), self._ceiling):
                withheld += 1
            else:
                visible.append(analysis)
        return visible, withheld

    # ── Direct read ───────────────────────────────────────────────────────────

    def apply_node(self, node: dict[str, Any] | None) -> Visible | NotFound:
        """Absent and above-ceiling are intentionally indistinguishable."""
        return self._apply_record(node)

    def apply_analysis(self, analysis: dict[str, Any] | None) -> Visible | NotFound:
        """Direct analysis read: absent and above-ceiling are indistinguishable."""
        return self._apply_record(analysis)

    def _apply_record(self, record: dict[str, Any] | None) -> Visible | NotFound:
        if record is None:
            return NotFound()
        if is_above_ceiling(str(record.get("tlp", "TLP:WHITE")), self._ceiling):
            return NotFound()
        return Visible(value=record, scope=self.scope())

    # ── Aggregate redaction ───────────────────────────────────────────────────

    def redact_stats(
        self,
        visible_nodes: list[dict[str, Any]],
        all_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Stats computed from visible nodes and their visible edges only."""
        visible_ids = frozenset(str(n["node_id"]) for n in visible_nodes)
        visible_edges = self.filter_edges(all_edges, visible_ids)
        by_type: dict[str, int] = {}
        for node in visible_nodes:
            t = str(node.get("node_type", ""))
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "node_count": len(visible_nodes),
            "edge_count": len(visible_edges),
            "by_type": by_type,
        }

    def redact_findings(
        self,
        findings: list[dict[str, Any]],
        visible_node_ids: frozenset[str],
    ) -> list[dict[str, Any]]:
        """Omit findings that reference a hidden node_id."""
        return [
            f for f in findings
            if "node_id" not in f or str(f["node_id"]) in visible_node_ids
        ]
