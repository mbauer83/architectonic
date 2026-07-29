"""WU-D1: the AIBOM read use case composes derivation + coverage over the read port, and
the schema-levels resolver reads required/recommended from the effective schemata."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.aibom_projection import aibom_schema_levels, project_aibom
from src.application.artifact_schema import clear_schema_cache
from src.domain.assurance.aibom_roles import role_bindings_from_mapping
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.repository.repo_default_attribute_schemata import ARCHIMATE_ATTRIBUTE_SCHEMATA


class _FakeSearch:
    """A minimal ArtifactSearch over in-memory records — no store, no IO."""

    def __init__(self, entities: list[EntityRecord], connections: list[ConnectionRecord]) -> None:
        self._entities = entities
        self._connections = connections

    def list_entities(self, **_kw) -> list[EntityRecord]:
        return self._entities

    def list_connections(self, **_kw) -> list[ConnectionRecord]:
        return self._connections


def _entity(
    artifact_id: str, artifact_type: str, *, specialization: str = "", attributes: dict | None = None
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id, artifact_type=artifact_type, name=artifact_id.split(".")[-1],
        version="0.1.0", status="draft", domain="application", subdomain="", path=Path(f"/{artifact_id}.md"),
        keywords=(), extra={}, content_text="", display_blocks={}, display_label="", display_alias="",
        specialization=specialization, attributes=attributes or {},
    )


def _bindings():
    return role_bindings_from_mapping(
        {
            "roles": {
                "trained-on": {"connection_types": ["archimate-access"], "target_specializations": ["ai-dataset"]},
                "governed-by": {"connection_types": ["archimate-assignment"], "target_specializations": []},
            }
        },
        label="test",
    )


def test_projection_derives_components_and_coverage() -> None:
    model = _entity("APP@1.a.model", "application-component", specialization="ai-model", attributes={"Task": "x"})
    search = _FakeSearch([model], [])
    projection = project_aibom(
        search, _bindings(), required_by_spec={"ai-model": ["Task", "Approach"]},
    )
    assert [c.entity_id for c in projection.components] == ["APP@1.a.model"]
    report = projection.coverage.components[0]
    assert report.missing_required_attributes == ("Approach",)  # Task authored, Approach not
    assert report.missing_dataset_linkage is True  # no trained-on connection


def test_projection_is_empty_for_a_model_with_no_ai_entities() -> None:
    search = _FakeSearch([_entity("APP@1.b.plain", "application-component")], [])
    projection = project_aibom(search, _bindings(), required_by_spec={})
    assert projection.components == ()
    assert projection.coverage.components == ()


def test_schema_levels_reads_required_and_recommended_from_effective_schema(tmp_path: Path) -> None:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    schemata = tmp_path / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True)
    for name, schema in ARCHIMATE_ATTRIBUTE_SCHEMATA.items():
        (schemata / name).write_text(json.dumps(schema), encoding="utf-8")
    clear_schema_cache()
    catalogs = build_runtime_catalogs(build_module_registry())
    required, recommended = aibom_schema_levels(tmp_path, catalogs)
    # ai-model's model card marks several attributes recommended; none is hard-required by
    # default (shipped guidance is advisory), so recommended is populated and required may be
    # empty — the point is the resolver reads the levels, keyed by AI specialization.
    assert "ai-model" in recommended
    assert "Task" in recommended["ai-model"]
    assert "Supplier" in recommended["ai-model"]  # from the bound ai-supplier profile
