"""WU-C1/C2: the ML-BOM builder emits a populated CycloneDX 1.6 document that VALIDATES
against the bundled CycloneDX 1.6 JSON schema — model card, component data, dependencies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.aibom_derivation import (
    AibomComponent,
    Considerations,
    MotivationRef,
    ProvenancedValue,
    RoleMatch,
)
from src.infrastructure.assurance.mlbom_builder import build_mlbom

_SCHEMA_PATH = Path(
    ".venv/lib/python3.14/site-packages/cyclonedx/schema/_res/bom-1.6.SNAPSHOT.schema.json"
)


@pytest.fixture(scope="module")
def validator():
    jsonschema = pytest.importorskip("jsonschema")
    if not _SCHEMA_PATH.is_file():
        pytest.skip("bundled CycloneDX 1.6 schema not present")
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft7Validator(schema)


def _authored(**kw: object) -> dict[str, ProvenancedValue]:
    return {k.replace("_", " ").title() if k.islower() else k: ProvenancedValue(v, "authored") for k, v in kw.items()}


def _model(**over) -> AibomComponent:
    base: dict[str, object] = dict(
        entity_id="APP@1.a.model", name="Fraud Model", specialization="ai-model",
        component_type="machine-learning-model",
    )
    base.update(over)
    return AibomComponent(**base)


def _dataset(entity_id: str = "DOB@1.b.data") -> AibomComponent:
    return AibomComponent(
        entity_id=entity_id, name="Training Set", specialization="ai-dataset", component_type="data",
        authored={"Sensitivity": ProvenancedValue("Confidential", "authored")},
        governance=(RoleMatch("governed-by", "BRL@1.g.owner", "Data Steward", ""),),
    )


def test_minimal_model_validates(validator) -> None:
    bom = build_mlbom([_model()])
    assert list(validator.iter_errors(bom)) == []
    assert bom["components"][0]["type"] == "machine-learning-model"


def test_full_model_card_validates(validator) -> None:
    model = _model(
        authored={
            "Approach": ProvenancedValue("Supervised", "authored"),
            "Task": ProvenancedValue("classification", "authored"),
            "Architecture Family": ProvenancedValue("transformer", "authored"),
            "Inputs": ProvenancedValue("text", "authored"),
            "Performance Metrics": ProvenancedValue(["accuracy 0.9"], "authored"),
            "Ethical Considerations": ProvenancedValue(["bias risk"], "authored"),
            "Technical Limitations": ProvenancedValue(["English only"], "authored"),
            "Supplier": ProvenancedValue("ACME", "authored"),
            "Licenses": ProvenancedValue(["Apache-2.0"], "authored"),
            "Hashes": ProvenancedValue(["sha256:abc"], "authored"),
        },
        datasets=(RoleMatch("trained-on", "DOB@1.b.data", "Training Set", "ai-dataset"),),
        governance=(RoleMatch("governed-by", "BRL@1.g.owner", "Model Owner", ""),),
        considerations=Considerations(
            users=(MotivationRef("STK@1.u.u", "Risk Analyst", "stakeholder"),),
            use_cases=(MotivationRef("DRV@1.d.d", "Detect Fraud", "driver"),),
        ),
    )
    bom = build_mlbom([model, _dataset()])
    assert list(validator.iter_errors(bom)) == []
    card = bom["components"][0]["modelCard"]
    assert card["modelParameters"]["approach"] == {"type": "supervised"}
    assert card["modelParameters"]["datasets"] == [{"ref": "DOB@1.b.data"}]
    assert card["considerations"]["users"] == ["Risk Analyst"]
    assert card["considerations"]["useCases"] == ["Detect Fraud"]
    assert bom["components"][0]["supplier"] == {"name": "ACME"}
    assert bom["components"][0]["licenses"] == [{"license": {"name": "Apache-2.0"}}]


def test_data_component_carries_classification_and_governance(validator) -> None:
    bom = build_mlbom([_dataset()])
    assert list(validator.iter_errors(bom)) == []
    data = bom["components"][0]["data"][0]
    assert data["type"] == "dataset"
    assert data["classification"] == "Confidential"
    assert data["governance"]["owners"] == [{"organization": {"name": "Data Steward"}}]


def test_dependencies_graph_is_emitted(validator) -> None:
    agent = _model(
        entity_id="APP@1.z.agent", name="Agent", specialization="ai-agent", component_type="application",
        dependency_ids=("APP@1.a.model",),
    )
    bom = build_mlbom([agent, _model()])
    assert list(validator.iter_errors(bom)) == []
    assert {"ref": "APP@1.z.agent", "dependsOn": ["APP@1.a.model"]} in bom["dependencies"]


def test_model_governance_without_a_data_home_becomes_a_property(validator) -> None:
    model = _model(governance=(RoleMatch("governed-by", "BRL@1.g.o", "Owner", ""),))
    bom = build_mlbom([model])
    assert list(validator.iter_errors(bom)) == []
    props = {p["name"]: p["value"] for p in bom["components"][0]["properties"]}
    assert props["arch:governed-by"] == "Owner"
    assert props["ai:specialization"] == "ai-model"
