"""Unit tests for the v2 guidance hierarchy contract (src/domain/guidance/guidance_hierarchy.py).

Covers level declaration + ordering, node identity, ancestry composition order, and the
build-time validation surface (undeclared level, duplicate node, missing/dangling parent,
non-total ordering), plus deterministic serialization and a module declaring a different
tree depth than archimate-4's domain→type→specialization three.
"""

from __future__ import annotations

from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy, GuidanceLevel, GuidanceNode


def _archimate_style() -> GuidanceHierarchy:
    return GuidanceHierarchy(
        levels=(
            GuidanceLevel("domain", "Domain", 0),
            GuidanceLevel("entity_type", "Entity type", 1),
            GuidanceLevel("specialization", "Specialization", 2),
        ),
        nodes=(
            GuidanceNode("domain", "strategy"),
            GuidanceNode("entity_type", "capability", parent_node_id="strategy"),
            GuidanceNode("specialization", "core-capability", parent_node_id="capability"),
        ),
    )


class TestLevels:
    def test_level_ids(self) -> None:
        assert _archimate_style().level_ids() == {"domain", "entity_type", "specialization"}

    def test_is_declared_level(self) -> None:
        h = _archimate_style()
        assert h.is_declared_level("domain")
        assert not h.is_declared_level("concern_class")

    def test_ordered_levels_sorts_by_order(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("b", "B", 2), GuidanceLevel("a", "A", 0), GuidanceLevel("m", "M", 1)),
            nodes=(),
        )
        assert [level.id for level in h.ordered_levels()] == ["a", "m", "b"]

    def test_parent_level_of_root_is_none(self) -> None:
        assert _archimate_style().parent_level_of("domain") is None

    def test_parent_level_of_middle_and_leaf(self) -> None:
        h = _archimate_style()
        assert h.parent_level_of("entity_type").id == "domain"  # type: ignore[union-attr]
        assert h.parent_level_of("specialization").id == "entity_type"  # type: ignore[union-attr]

    def test_parent_level_of_undeclared_is_none(self) -> None:
        assert _archimate_style().parent_level_of("nope") is None


class TestAncestry:
    def test_full_path_is_root_first(self) -> None:
        chain = _archimate_style().ancestry("specialization", "core-capability")
        assert [(n.level_id, n.node_id) for n in chain] == [
            ("domain", "strategy"),
            ("entity_type", "capability"),
            ("specialization", "core-capability"),
        ]

    def test_ancestry_of_root_node_is_itself(self) -> None:
        chain = _archimate_style().ancestry("domain", "strategy")
        assert [(n.level_id, n.node_id) for n in chain] == [("domain", "strategy")]

    def test_unknown_node_has_empty_ancestry(self) -> None:
        assert _archimate_style().ancestry("entity_type", "ghost") == ()


class TestValidation:
    def test_sound_tree_has_no_errors(self) -> None:
        assert _archimate_style().validation_errors() == ()

    def test_duplicate_level_id(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("d", "D", 0), GuidanceLevel("d", "D2", 1)),
            nodes=(),
        )
        assert any("duplicate level id 'd'" in e for e in h.validation_errors())

    def test_non_total_ordering(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("a", "A", 0), GuidanceLevel("b", "B", 0)),
            nodes=(),
        )
        assert any("total order" in e for e in h.validation_errors())

    def test_node_on_undeclared_level(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("domain", "Domain", 0),),
            nodes=(GuidanceNode("ghostlevel", "x"),),
        )
        assert any("undeclared level" in e for e in h.validation_errors())

    def test_duplicate_node(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("domain", "Domain", 0),),
            nodes=(GuidanceNode("domain", "strategy"), GuidanceNode("domain", "strategy")),
        )
        assert any("duplicate node domain/strategy" in e for e in h.validation_errors())

    def test_missing_parent(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("domain", "Domain", 0), GuidanceLevel("entity_type", "T", 1)),
            nodes=(GuidanceNode("entity_type", "capability"),),  # no parent_node_id
        )
        assert any("missing a parent" in e for e in h.validation_errors())

    def test_dangling_parent_reference(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("domain", "Domain", 0), GuidanceLevel("entity_type", "T", 1)),
            nodes=(GuidanceNode("entity_type", "capability", parent_node_id="ghost"),),
        )
        assert any("references missing parent domain/ghost" in e for e in h.validation_errors())

    def test_root_node_must_not_declare_parent(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("domain", "Domain", 0),),
            nodes=(GuidanceNode("domain", "strategy", parent_node_id="oops"),),
        )
        assert any("must not declare a parent" in e for e in h.validation_errors())


class TestDifferentTreeDepth:
    def test_two_level_module_validates_and_composes(self) -> None:
        h = GuidanceHierarchy(
            levels=(GuidanceLevel("concern_class", "Concern class", 0), GuidanceLevel("entity_type", "T", 1)),
            nodes=(
                GuidanceNode("concern_class", "safety"),
                GuidanceNode("entity_type", "hazard", parent_node_id="safety"),
            ),
        )
        assert h.validation_errors() == ()
        chain = h.ancestry("entity_type", "hazard")
        assert [n.node_id for n in chain] == ["safety", "hazard"]


class TestSerialization:
    def test_serializable_is_deterministic_and_ordered(self) -> None:
        a = _archimate_style().to_serializable()
        b = _archimate_style().to_serializable()
        assert a == b
        assert [level["id"] for level in a["levels"]] == ["domain", "entity_type", "specialization"]
        keys = [(n["level_id"], n["node_id"]) for n in a["nodes"]]
        assert keys == sorted(keys)
