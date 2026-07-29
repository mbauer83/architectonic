"""Tests for AI-BOM export (CycloneDX 1.6) and reconcile."""

from __future__ import annotations

from src.infrastructure.assurance._aibom_exporter import build_cyclonedx_16, reconcile_aibom


def _comp(name: str, ai_role: str = "machine-learning-model", purl: str = "") -> dict:
    return {"name": name, "ai_role": ai_role, "purl": purl, "version": "1.0"}


class TestBuildCycloneDX16:
    def test_envelope_structure(self) -> None:
        bom = build_cyclonedx_16([])
        assert bom["bomFormat"] == "CycloneDX"
        assert bom["specVersion"] == "1.6"
        assert "serialNumber" in bom
        assert bom["components"] == []

    def test_component_type_mapping(self) -> None:
        comps = [
            _comp("my-llm", "machine-learning-model"),
            _comp("my-dataset", "dataset"),
            _comp("my-mcp", "mcp-server"),
            _comp("my-agent", "agent"),
        ]
        bom = build_cyclonedx_16(comps)
        cdx_comps = bom["components"]
        assert cdx_comps[0]["type"] == "machine-learning-model"
        assert cdx_comps[1]["type"] == "data"
        assert cdx_comps[2]["type"] == "service"
        assert cdx_comps[3]["type"] == "application"

    def test_ai_role_property(self) -> None:
        bom = build_cyclonedx_16([_comp("gpt", "machine-learning-model")])
        props = bom["components"][0]["properties"]
        assert any(p["name"] == "ai:role" for p in props)

    def test_purl_included(self) -> None:
        bom = build_cyclonedx_16([_comp("lib", "tool", "pkg:npm/lib@1.0")])
        assert bom["components"][0]["purl"] == "pkg:npm/lib@1.0"

    def test_serial_override(self) -> None:
        bom = build_cyclonedx_16([], serial="urn:uuid:my-serial")
        assert bom["serialNumber"] == "urn:uuid:my-serial"

    def test_notes_in_metadata(self) -> None:
        bom = build_cyclonedx_16([], notes="test release")
        assert bom["metadata"]["notes"] == "test release"

    def test_arch_entity_id_property(self) -> None:
        comp = {"name": "svc", "ai_role": "inference-service", "arch_entity_id": "ACP@123"}
        bom = build_cyclonedx_16([comp])
        props = bom["components"][0]["properties"]
        assert any(p["name"] == "arch:entity_id" and p["value"] == "ACP@123" for p in props)

    def test_unknown_ai_role_defaults_to_library(self) -> None:
        bom = build_cyclonedx_16([{"name": "x", "ai_role": "unknown-role"}])
        assert bom["components"][0]["type"] == "library"


class TestReconcileAiBom:
    def _c(self, name: str, purl: str = "") -> dict:
        return {"name": name, "purl": purl}

    def test_all_matched(self) -> None:
        comps = [self._c("a", "pkg:npm/a@1"), self._c("b", "pkg:npm/b@1")]
        result = reconcile_aibom(comps, comps)
        assert result["added_count"] == 0
        assert result["removed_count"] == 0
        assert result["matched_count"] == 2

    def test_added_in_discovered(self) -> None:
        modeled = [self._c("a", "pkg:npm/a@1")]
        discovered = [self._c("a", "pkg:npm/a@1"), self._c("b", "pkg:npm/b@1")]
        result = reconcile_aibom(modeled, discovered)
        assert result["added_count"] == 1
        assert result["added"][0]["name"] == "b"

    def test_removed_from_modeled(self) -> None:
        modeled = [self._c("a", "pkg:npm/a@1"), self._c("old", "pkg:npm/old@1")]
        discovered = [self._c("a", "pkg:npm/a@1")]
        result = reconcile_aibom(modeled, discovered)
        assert result["removed_count"] == 1
        assert result["removed"][0]["name"] == "old"

    def test_name_fallback_key_when_no_purl(self) -> None:
        modeled = [{"name": "mymodel"}]
        discovered = [{"name": "mymodel"}]
        result = reconcile_aibom(modeled, discovered)
        assert result["matched_count"] == 1

    def test_empty_both(self) -> None:
        result = reconcile_aibom([], [])
        assert result["added_count"] == 0
        assert result["removed_count"] == 0
        assert result["matched_count"] == 0

    def test_reconcile_over_the_new_mlbom_component_shape(self) -> None:
        # WU-C3: reconcile keys by name (no purl on derived AI components), so it works over
        # the richer ML-BOM nodes build_mlbom emits — a discovered extra shows as added.
        from src.application.aibom_derivation import AibomComponent
        from src.infrastructure.assurance.mlbom_builder import build_mlbom

        model = AibomComponent(
            entity_id="APP@1.a.model", name="Fraud Model", specialization="ai-model",
            component_type="machine-learning-model",
        )
        extra = AibomComponent(
            entity_id="APP@1.b.agent", name="Agent", specialization="ai-agent",
            component_type="application",
        )
        modeled = build_mlbom([model])["components"]
        discovered = build_mlbom([model, extra])["components"]
        result = reconcile_aibom(modeled, discovered)
        assert result["matched_count"] == 1
        assert result["added_count"] == 1
        assert result["added"][0]["name"] == "Agent"
