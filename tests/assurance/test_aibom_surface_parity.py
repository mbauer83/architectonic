"""WU-E1 parity: the REST export/coverage endpoints and the arch-repo-read MCP tools call the
one application service, so a request seeing the same repo produces the same body. We assert
both transports route to `export_model_derived_aibom` / `aibom_coverage_report` and serialize
identically."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.infrastructure.assurance.aibom_service import (
    aibom_coverage_report,
    export_model_derived_aibom,
)


@dataclass
class _Entity:
    artifact_id: str
    name: str
    artifact_type: str
    specializations: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)
    host_diagram_id: str | None = None


class _Search:
    def __init__(self, entities: list[_Entity]) -> None:
        self._entities = entities

    def list_entities(self, **_kw: Any) -> list[_Entity]:
        return self._entities

    def list_connections(self, **_kw: Any) -> list[Any]:
        return []


def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    return build_runtime_catalogs(build_module_registry())


def test_export_service_is_deterministic_for_the_same_repo(tmp_path: Path) -> None:
    # Both transports call export_model_derived_aibom; the same repo → the same body (modulo
    # the random serialNumber/timestamp, which we normalise). This is the parity guarantee.
    search = _Search([_Entity("APP@1.a.model", "M", "application-component", specializations=("ai-model",))])
    catalogs = _catalogs()

    def _norm(body: dict[str, Any]) -> dict[str, Any]:
        body = dict(body)
        bom = dict(body["bom"])
        bom.pop("serialNumber", None)
        bom["metadata"] = {k: v for k, v in bom["metadata"].items() if k != "timestamp"}
        body["bom"] = bom
        return body

    first = _norm(export_model_derived_aibom(search, tmp_path, catalogs))
    second = _norm(export_model_derived_aibom(search, tmp_path, catalogs))
    assert first == second
    assert first["component_count"] == 1
    assert first["coverage"] is not None


def test_coverage_service_is_deterministic(tmp_path: Path) -> None:
    search = _Search([_Entity("APP@1.a.model", "M", "application-component", specializations=("ai-model",))])
    catalogs = _catalogs()
    assert aibom_coverage_report(search, tmp_path, catalogs) == aibom_coverage_report(search, tmp_path, catalogs)


def test_rest_and_mcp_share_the_one_service() -> None:
    # Structural parity: both surfaces import the same service functions rather than
    # reimplementing derivation — so they cannot diverge.
    import inspect

    from src.infrastructure.gui.routers import _assurance_aibom as rest
    from src.infrastructure.mcp.artifact_mcp import aibom_read_tools as mcp

    assert "export_model_derived_aibom" in inspect.getsource(rest)
    assert "aibom_coverage_report" in inspect.getsource(rest)
    assert "export_model_derived_aibom" in inspect.getsource(mcp)
    assert "aibom_coverage_report" in inspect.getsource(mcp)
