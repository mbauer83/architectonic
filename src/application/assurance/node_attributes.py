"""Reading a store node's attribute blob — one implementation, for every consumer.

The confidential store returns a node as a flat dict of its columns plus `attributes_json`, a JSON
blob holding everything the schema declares rather than the table does. A consumer that reads an
attribute as though it were a column finds `None`, silently: the value is present, spelled exactly
as expected, one level down.

That is not a hypothetical. The failure-mode matrix read `assessment_state` flatly, so a cell
examined and dismissed came back indistinguishable from one carrying a real failure mode — the
third cell state existed in the code and could not be reached through the store. Its unit test
passed because it hand-built a node with the attribute at the top level, which is a shape the store
never produces.
"""

from __future__ import annotations

import json
from collections.abc import Mapping


def attributes_of(node: Mapping[str, object]) -> dict[str, object]:
    """The node's attribute blob, or an empty mapping when it is absent or unparseable.

    An unparseable blob yields no attributes rather than raising: a corrupt row should not stop the
    rest of the store being read or verified, and a consumer that handles absence correctly handles
    this correctly too.
    """
    raw = node.get("attributes_json") or "{}"
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def attribute(node: Mapping[str, object], name: str) -> object | None:
    """One declared attribute of a node, looked up where it actually lives.

    Falls back to the top level so a caller may pass a node assembled in memory — a projection, or
    a record built for a test — without every consumer needing to know which shape it holds.
    """
    found = attributes_of(node).get(name)
    return node.get(name) if found is None else found
