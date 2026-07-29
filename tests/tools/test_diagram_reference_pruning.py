"""Unit tests for pruning dangling diagram references.

After an entity rename (slug change) or delete, a scope-bound diagram's cached
entity-ids-used / connection-ids-used can reference ids that no longer resolve, failing
verification (E301/E302) and making the diagram unwritable. The diagram writer prunes such
references so a re-projection self-heals, while preserving valid (incl. cross-repo) refs and
never stripping refs when the registry is unavailable or its id set is empty.
"""

from __future__ import annotations

from src.infrastructure.write.artifact_write.diagram_references import _prune_unknown_references


class _FakeRegistry:
    def __init__(self, entities: set[str], connections: set[str]) -> None:
        self._entities = entities
        self._connections = connections

    def entity_ids(self) -> set[str]:
        return self._entities

    def connection_ids(self) -> set[str]:
        return self._connections


def test_drops_unknown_entity_and_connection_refs() -> None:
    reg = _FakeRegistry({"APP@1.a.keep", "APP@2.b.keep"}, {"APP@1.a.keep---APP@2.b.keep@@serving"})

    entities, connections = _prune_unknown_references(
        reg,
        ["APP@1.a.keep", "APP@9.z.renamed-away", "APP@2.b.keep"],
        ["APP@1.a.keep---APP@2.b.keep@@serving", "APP@1.a.keep---APP@9.z.renamed-away@@serving"],
    )

    assert entities == ["APP@1.a.keep", "APP@2.b.keep"]
    assert connections == ["APP@1.a.keep---APP@2.b.keep@@serving"]


def test_none_registry_is_passthrough() -> None:
    entities, connections = _prune_unknown_references(None, ["APP@1.a.x"], ["APP@1.a.x---APP@2.b.y@@t"])

    assert entities == ["APP@1.a.x"]
    assert connections == ["APP@1.a.x---APP@2.b.y@@t"]


def test_empty_registry_never_over_prunes() -> None:
    reg = _FakeRegistry(set(), set())

    entities, connections = _prune_unknown_references(reg, ["APP@1.a.x"], ["APP@1.a.x---APP@2.b.y@@t"])

    assert entities == ["APP@1.a.x"]
    assert connections == ["APP@1.a.x---APP@2.b.y@@t"]
