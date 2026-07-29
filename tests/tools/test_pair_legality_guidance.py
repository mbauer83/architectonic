"""Tests for pair-legality guidance in artifact_authoring_guidance.

Covers:
- domain helper pair_connection_guidance returns outgoing/incoming/symmetric
- get_type_guidance with target parameter
- validation: target without filter → error
- validation: filter with domain name + target → error
- validation: filter with multiple types + target → error
- unknown types return error with suggestions
- results consistent with REST /api/ontology (parity test)
- MCP artifact_authoring_guidance passes target through
"""

from __future__ import annotations

from functools import lru_cache

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.type_guidance import (
    get_type_guidance,
    pair_connection_guidance,
)


@lru_cache(maxsize=1)
def _catalogs() -> RuntimeCatalogs:
    return build_runtime_catalogs(build_module_registry())

# ---------------------------------------------------------------------------
# domain helper: pair_connection_guidance
# ---------------------------------------------------------------------------


class TestPairConnectionGuidanceDomain:
    def test_returns_required_keys(self) -> None:
        result = pair_connection_guidance("requirement", "goal")
        assert "source" in result
        assert "target" in result
        assert "outgoing" in result
        assert "incoming" in result
        assert "symmetric" in result

    def test_source_target_values_match_inputs(self) -> None:
        result = pair_connection_guidance("requirement", "driver")
        assert result["source"] == "requirement"
        assert result["target"] == "driver"

    def test_unknown_source_returns_error(self) -> None:
        result = pair_connection_guidance("not-a-type", "goal")
        assert "error" in result
        assert "known_types" in result

    def test_unknown_target_returns_error(self) -> None:
        result = pair_connection_guidance("requirement", "not-a-type")
        assert "error" in result

    def test_both_unknown_returns_error(self) -> None:
        result = pair_connection_guidance("x", "y")
        assert "error" in result

    def test_all_fields_are_sorted_lists(self) -> None:
        result = pair_connection_guidance("application-component", "data-object")
        assert isinstance(result["outgoing"], list)
        assert isinstance(result["incoming"], list)
        assert isinstance(result["symmetric"], list)
        assert result["outgoing"] == sorted(result["outgoing"])
        assert result["incoming"] == sorted(result["incoming"])
        assert result["symmetric"] == sorted(result["symmetric"])

    def test_outgoing_and_symmetric_disjoint(self) -> None:
        result = pair_connection_guidance("application-component", "data-object")
        out_set = set(result["outgoing"])
        sym_set = set(result["symmetric"])
        assert out_set.isdisjoint(sym_set), "outgoing and symmetric must be disjoint"

    def test_parity_with_permissible_connection_types(self) -> None:
        """outgoing + symmetric should equal permissible_connection_types(source, target)."""
        source, target = "requirement", "goal"
        pg = pair_connection_guidance(source, target)
        assert "error" not in pg

        rest_equiv = set(_catalogs().connections.permissible_connection_types(source, target))
        guidance_source_to_target = set(pg["outgoing"]) | set(pg["symmetric"])
        assert guidance_source_to_target == rest_equiv, (
            f"pair_guidance (outgoing+symmetric) {sorted(guidance_source_to_target)!r} "
            f"!= permissible_connection_types {sorted(rest_equiv)!r}"
        )


# ---------------------------------------------------------------------------
# get_type_guidance with target
# ---------------------------------------------------------------------------


class TestGetTypeGuidanceWithTarget:
    def test_valid_request_returns_pair_guidance_block(self) -> None:
        result = get_type_guidance(filter=["requirement"], target="goal")
        assert "pair_guidance" in result
        pg = result["pair_guidance"]
        assert pg["source"] == "requirement"
        assert pg["target"] == "goal"

    def test_entity_type_guidance_also_returned(self) -> None:
        result = get_type_guidance(filter=["requirement"], target="goal")
        assert "entity_types" in result
        assert any(e["name"] == "requirement" for e in result["entity_types"])

    def test_target_without_filter_is_error(self) -> None:
        result = get_type_guidance(target="goal")
        assert "error" in result
        assert "pair_guidance" not in result

    def test_target_with_domain_filter_is_error(self) -> None:
        result = get_type_guidance(filter=["motivation"], target="goal")
        assert "error" in result

    def test_target_with_multiple_types_is_error(self) -> None:
        result = get_type_guidance(filter=["requirement", "goal"], target="driver")
        assert "error" in result

    def test_unknown_target_returns_error_in_pair_guidance(self) -> None:
        result = get_type_guidance(filter=["requirement"], target="not-a-type")
        assert "pair_guidance" in result
        assert "error" in result["pair_guidance"]

    def test_symmetric_connections_have_symmetric_flag(self) -> None:
        """Every connection in pair_guidance.symmetric must be symmetric per the registry."""
        result = get_type_guidance(filter=["application-component"], target="data-object")
        pg = result.get("pair_guidance", {})
        if "error" in pg:
            return
        for ct in pg["symmetric"]:
            assert _catalogs().connections.is_symmetric(ct), f"{ct!r} in symmetric is not symmetric per is_symmetric()"

    def test_no_target_returns_normal_guidance(self) -> None:
        """Calling without target must not add pair_guidance or error."""
        result = get_type_guidance(filter=["requirement"])
        assert "pair_guidance" not in result
        assert "error" not in result
        assert "entity_types" in result


# ---------------------------------------------------------------------------
# MCP artifact_authoring_guidance passes target through
# ---------------------------------------------------------------------------


class TestMcpAuthoringGuidancePairLegality:
    def test_mcp_target_returns_pair_guidance(self) -> None:
        result = mcp.artifact_authoring_guidance(
            filter=["requirement"],
            target="goal",
        )
        assert "pair_guidance" in result
        pg = result["pair_guidance"]
        assert pg["source"] == "requirement"
        assert pg["target"] == "goal"
        assert "outgoing" in pg
        assert "incoming" in pg
        assert "symmetric" in pg

    def test_mcp_target_without_filter_returns_error(self) -> None:
        result = mcp.artifact_authoring_guidance(target="goal")
        assert "error" in result

    def test_mcp_target_with_domain_filter_returns_error(self) -> None:
        result = mcp.artifact_authoring_guidance(filter=["motivation"], target="goal")
        assert "error" in result

    def test_mcp_normal_call_unaffected(self) -> None:
        result = mcp.artifact_authoring_guidance(filter=["requirement"])
        assert "pair_guidance" not in result
        assert "entity_types" in result


# ---------------------------------------------------------------------------
# REST /api/ontology endpoint parity
# ---------------------------------------------------------------------------


def _ontology_rest_client():
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
    from src.infrastructure.gui.routers.connections import router as connections_router

    app = FastAPI()
    app.dependency_overrides[runtime_catalogs_dependency] = _catalogs
    app.include_router(connections_router)
    return TestClient(app)


class TestRestOntologyEndpointParity:
    """The pair_connection_guidance domain function must agree with /api/ontology REST output."""

    def test_rest_ontology_endpoint_returns_connection_types(self) -> None:
        client = _ontology_rest_client()

        response = client.get("/api/ontology", params={"source_type": "requirement", "target_type": "goal"})
        assert "connection_types" in response.json(), (
            "REST /api/ontology with source+target must return connection_types"
        )

    def test_rest_and_domain_agree_on_permitted_types(self) -> None:
        """REST /api/ontology and pair_connection_guidance outgoing+symmetric must cover the same types."""
        client = _ontology_rest_client()

        source, target = "application-component", "data-object"
        pg = pair_connection_guidance(source, target)
        guidance_types = set(pg.get("outgoing", [])) | set(pg.get("symmetric", []))

        response = client.get("/api/ontology", params={"source_type": source, "target_type": target})
        rest_types = set(response.json().get("connection_types", []))

        assert guidance_types == rest_types, (
            f"Pair guidance (outgoing+symmetric) {sorted(guidance_types)!r} "
            f"differs from REST connection_types {sorted(rest_types)!r}"
        )
