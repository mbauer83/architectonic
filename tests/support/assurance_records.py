"""Whole assurance records for test fakes, so a fake cannot describe a shape no store returns.

Every ``_FakeStore`` in the assurance HTTP tests built node rows by hand, and each built a different
subset — two keys here, five there. That was invisible while the responses were untyped: the handler
passed whatever it was given straight out, so a test could assert a body no deployment produces. Once
the routes serve closed DTOs derived from the real store, those partial rows fail validation, and the
right fix is for the fakes to return what a store returns rather than for the contract to widen.

Field defaults come from the canonical tuples, so a field added to a record reaches every fake at
once instead of nine modules failing one at a time.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.assurance._analysis_records import ANALYSIS_RECORD_FIELDS
from src.infrastructure.assurance._edge_records import EDGE_RECORD_FIELDS
from src.infrastructure.assurance._node_records import NODE_RECORD_FIELDS

_STAMP = "2026-01-01T00:00:00Z"

#: Non-null defaults for the fields a stored node always has a value for. Everything else in
#: ``NODE_RECORD_FIELDS`` is a discriminator and defaults to ``None``, which is what an unset one is.
_NODE_DEFAULTS: dict[str, Any] = {
    "node_id": "LSS@1.aaaa.000001",
    "node_type": "loss",
    "name": "A loss",
    "status": "draft",
    "tlp": "TLP:WHITE",
    "attributes_json": "{}",
    "content_text": "",
    "created_at": _STAMP,
    "updated_at": _STAMP,
}

_EDGE_DEFAULTS: dict[str, Any] = {
    "edge_id": "EDG@aaaaaaaaaaaa",
    "source_id": _NODE_DEFAULTS["node_id"],
    "target_id": "HAZ@1.bbbb.000002",
    "conn_type": "leads-to",
    "attributes_json": "{}",
    "created_at": _STAMP,
}

_ANALYSIS_DEFAULTS: dict[str, Any] = {
    "analysis_id": "STPA@1.cccc.000003",
    "group_id": None,
    "name": "An analysis",
    "method": "STPA",
    "architecture_anchor_id": "",
    "status": "draft",
    "tlp": "TLP:WHITE",
    "created_at": _STAMP,
    "updated_at": _STAMP,
}


def _record(fields: tuple[str, ...], defaults: dict[str, Any], overrides: Any) -> dict[str, Any]:
    unknown = set(overrides) - set(fields)
    if unknown:
        raise AssertionError(
            f"not fields of this record: {sorted(unknown)} — a fake that invents one describes a "
            "shape no store returns, which is the defect these helpers exist to prevent"
        )
    return {field: overrides.get(field, defaults.get(field)) for field in fields}


def node_record(**overrides: Any) -> dict[str, Any]:
    """A whole node record, with the discriminators null unless named."""
    return _record(NODE_RECORD_FIELDS, _NODE_DEFAULTS, overrides)


def edge_record(**overrides: Any) -> dict[str, Any]:
    """A whole edge record."""
    return _record(EDGE_RECORD_FIELDS, _EDGE_DEFAULTS, overrides)


def analysis_record(**overrides: Any) -> dict[str, Any]:
    """A whole analysis record, unfiled unless a ``group_id`` is named."""
    return _record(ANALYSIS_RECORD_FIELDS, _ANALYSIS_DEFAULTS, overrides)
