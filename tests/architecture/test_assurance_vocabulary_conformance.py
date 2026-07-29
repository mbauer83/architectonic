"""The assurance vocabularies stated in the domain must match what the ontology declares.

The layering rules keep the application layer out of the ontology packages, so the creatable node
types are stated as a domain fact and pinned here. Without this pin the statement is a copy, and a
copy of a vocabulary inside a validation gate fails in one direction only: the gate rejects the
value that is missing from it, so a type the ontology declares and every read surface renders is
simply uncreatable, with no error anywhere that names the real cause.

That is not hypothetical — it is how `failure-mode` came to be declared, stored, rendered and
rejected at the same time.
"""

from __future__ import annotations

import pytest

from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS
from src.domain.assurance.assurance_node_types import CREATABLE_NODE_TYPES, NODE_ID_PREFIXES


def _assurance_entity_types() -> frozenset[str]:
    from src.ontologies.assurance import module  # noqa: PLC0415

    return frozenset(str(name) for name in module.entity_types)


def _declared_prefixes() -> dict[str, str]:
    from src.ontologies.assurance import module  # noqa: PLC0415

    return {str(name): str(info.prefix) for name, info in module.entity_types.items()}


class TestIdPrefixesMatchTheOntology:
    """An id is persisted, so a wrong prefix is permanent and nothing about it looks wrong."""

    def test_every_type_carries_its_declared_prefix(self) -> None:
        disagreeing = {
            name: (NODE_ID_PREFIXES.get(name), declared)
            for name, declared in _declared_prefixes().items()
            if NODE_ID_PREFIXES.get(name) != declared
        }

        assert not disagreeing, f"prefix (allocated, declared) mismatch: {disagreeing}"

    def test_no_prefix_is_declared_for_a_type_that_does_not_exist(self) -> None:
        assert not set(NODE_ID_PREFIXES) - _assurance_entity_types()

    def test_allocation_refuses_an_undeclared_type(self) -> None:
        """The fallback this replaces invented a prefix from the type name and persisted it."""
        from src.infrastructure.assurance._id_utils import make_node_id  # noqa: PLC0415

        with pytest.raises(ValueError, match="No id prefix is declared"):
            make_node_id("not-a-node-type", "whatever")


class TestCreatableNodeTypesMatchTheOntology:
    def test_every_declared_entity_type_can_be_created(self) -> None:
        missing = _assurance_entity_types() - CREATABLE_NODE_TYPES
        assert not missing, (
            f"the ontology declares {sorted(missing)} but the write path rejects them — "
            "a node type nobody can create"
        )

    def test_no_creatable_type_is_undeclared(self) -> None:
        """The other direction: a type the write path accepts but the ontology does not know is
        stored with no guidance, no legality matrix rows and no read surface."""
        undeclared = CREATABLE_NODE_TYPES - _assurance_entity_types()
        assert not undeclared, f"{sorted(undeclared)} accepted for creation but undeclared"


class TestTheWriteToolsDescribeWhatTheyAccept:
    """An agent picks a node type from the tool description alone. A type absent from it is
    reachable only by guessing, which is the same as not shipping it."""

    def _tool(self, name: str) -> object:
        from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_write  # noqa: PLC0415

        tools = {t.name: t for t in mcp_assurance_write._tool_manager.list_tools()}  # type: ignore[attr-defined]
        assert name in tools, f"{name} not registered"
        return tools[name]

    def test_create_node_names_every_creatable_type(self) -> None:
        description = str(self._tool("assurance_create_node").description)  # type: ignore[attr-defined]
        unnamed = sorted(t for t in CREATABLE_NODE_TYPES if t not in description)

        assert not unnamed, f"assurance_create_node does not mention {unnamed}"

    def test_create_analysis_names_every_method(self) -> None:
        description = str(self._tool("assurance_create_analysis").description)  # type: ignore[attr-defined]
        unnamed = sorted(m for m in ANALYSIS_METHODS if m not in description)

        assert not unnamed, f"assurance_create_analysis does not mention {unnamed}"


class TestTheReadSurfaceSupportsTheWriteSurface:
    """`assurance_set_fmea_factor` demands a `basis_digest` and an assertion applies only while that
    digest matches, so it is unusable unless a read publishes it. Both reads that do are pinned here:
    without them the write tool ships as a tool nobody can call correctly."""

    def _read_tools(self) -> dict[str, object]:
        from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read  # noqa: PLC0415

        return {t.name: t for t in mcp_assurance_read._tool_manager.list_tools()}  # type: ignore[attr-defined]

    def test_the_matrix_is_readable(self) -> None:
        """The candidate set and untouched cells are reachable no other way — `assurance_verify`
        is silenced by the first failure mode recorded against an element."""
        assert "assurance_fmea_matrix" in self._read_tools()

    def test_the_matrix_description_names_the_digest(self) -> None:
        description = str(self._read_tools()["assurance_fmea_matrix"].description)  # type: ignore[attr-defined]

        assert "basis_digest" in description

    def test_reading_a_node_offers_the_factor_report(self) -> None:
        description = str(self._read_tools()["assurance_read_node"].description)  # type: ignore[attr-defined]

        assert "factor_report" in description
        assert "basis_digest" in description
