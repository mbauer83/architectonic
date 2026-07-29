"""Build a CycloneDX 1.6 ML-BOM from derived AIBOM components (PLAN Stream C / WU-C1).

Turns the typed `AibomComponent` set (from the pure derivation core) into a schema-valid
CycloneDX 1.6 document: a populated `modelCard` on model components, `componentData` with
classification and governance on data components, `supplier` / `licenses`, and a real
`dependencies[]` graph. Anything without a clean CycloneDX home is emitted as an `arch:` /
`ai:` property rather than forced into an ill-fitting field, so the document stays valid.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from src.application.aibom_derivation import AibomComponent, ProvenancedValue
from src.domain.clock import utc_now_iso

# Authored "Approach" (Title Case enum) → CycloneDX learning-type enum.
_APPROACH = {
    "Supervised": "supervised",
    "Unsupervised": "unsupervised",
    "Semi-supervised": "semi-supervised",
    "Self-supervised": "self-supervised",
    "Reinforcement Learning": "reinforcement-learning",
}
_MODEL_TYPES = frozenset({"machine-learning-model"})
_DATA_TYPES = frozenset({"data"})


def build_mlbom(
    components: Sequence[AibomComponent], *, serial: str | None = None, notes: str = ""
) -> dict[str, Any]:
    """Emit a CycloneDX 1.6 ML-BOM. ``bom-ref`` is each component's entity id, so the
    ``dependencies[]`` graph and dataset ``ref``s resolve within the document."""
    metadata: dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "tools": [{"name": "arch-assurance", "version": "1.0"}],
    }
    if notes:
        # CycloneDX metadata has no free 'notes' field; carry it as a metadata property.
        metadata["properties"] = [{"name": "arch:notes", "value": notes}]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": serial or f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": metadata,
        "components": [_component_node(c) for c in components],
        "dependencies": _dependencies(components),
    }


def _val(comp: AibomComponent, key: str) -> Any:
    pv = comp.authored.get(key)
    return pv.value if isinstance(pv, ProvenancedValue) else None


def _str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v)]
    return [str(value)] if value else []


def _component_node(comp: AibomComponent) -> dict[str, Any]:
    node: dict[str, Any] = {"type": comp.component_type, "name": comp.name, "bom-ref": comp.entity_id}
    supplier = _val(comp, "Supplier")
    if supplier:
        node["supplier"] = {"name": str(supplier)}
    licenses = _str_list(_val(comp, "Licenses"))
    if licenses:
        node["licenses"] = [{"license": {"name": lic}} for lic in licenses]
    if comp.component_type in _MODEL_TYPES:
        node["modelCard"] = _model_card(comp)
    if comp.component_type in _DATA_TYPES:
        node["data"] = [_component_data(comp)]
    props = _properties(comp)
    if props:
        node["properties"] = props
    return node


def _model_card(comp: AibomComponent) -> dict[str, Any]:
    params: dict[str, Any] = {}
    approach = _APPROACH.get(str(_val(comp, "Approach") or ""))
    if approach:
        params["approach"] = {"type": approach}
    for key, field in (("Task", "task"), ("Architecture Family", "architectureFamily"),
                        ("Model Architecture", "modelArchitecture")):
        value = _val(comp, key)
        if value:
            params[field] = str(value)
    if comp.datasets:
        params["datasets"] = [{"ref": d.target_entity_id} for d in comp.datasets]
    for key, field in (("Inputs", "inputs"), ("Outputs", "outputs")):
        value = _val(comp, key)
        if value:
            params[field] = [{"format": str(value)}]
    card: dict[str, Any] = {}
    if params:
        card["modelParameters"] = params
    metrics = _str_list(_val(comp, "Performance Metrics"))
    if metrics:
        card["quantitativeAnalysis"] = {"performanceMetrics": [{"type": m} for m in metrics]}
    considerations = _considerations(comp)
    if considerations:
        card["considerations"] = considerations
    return card


def _considerations(comp: AibomComponent) -> dict[str, Any]:
    out: dict[str, Any] = {}
    users = [u.name for u in comp.considerations.users]
    use_cases = [u.name for u in comp.considerations.use_cases]
    if users:
        out["users"] = users
    if use_cases:
        out["useCases"] = use_cases
    for key, field in (("Technical Limitations", "technicalLimitations"),
                       ("Performance Tradeoffs", "performanceTradeoffs")):
        values = _str_list(_val(comp, key))
        if values:
            out[field] = values
    ethical = _str_list(_val(comp, "Ethical Considerations"))
    if ethical:
        out["ethicalConsiderations"] = [{"name": e} for e in ethical]
    return out


def _component_data(comp: AibomComponent) -> dict[str, Any]:
    data: dict[str, Any] = {"type": "dataset", "name": comp.name}
    classification = _val(comp, "Sensitivity")
    if classification:
        data["classification"] = str(classification)
    governance = _governance(comp)
    if governance:
        data["governance"] = governance
    return data


def _governance(comp: AibomComponent) -> dict[str, Any]:
    owners = [{"organization": {"name": g.target_name}} for g in comp.governance]
    return {"owners": owners} if owners else {}


def _properties(comp: AibomComponent) -> list[dict[str, str]]:
    """Fields with no clean CycloneDX home, kept honest as prefixed properties: the
    specialization, governance on a non-data component, and the flat extras."""
    props: list[dict[str, str]] = [{"name": "ai:specialization", "value": comp.specialization}]
    if comp.component_type not in _DATA_TYPES:
        for g in comp.governance:
            props.append({"name": "arch:governed-by", "value": g.target_name})
    for key, name in (("Publisher", "ai:publisher"), ("Control Flow", "ai:control-flow"),
                      ("Dataset Role", "ai:dataset-role")):
        value = _val(comp, key)
        if value:
            props.append({"name": name, "value": str(value)})
    for h in _str_list(_val(comp, "Hashes")):
        props.append({"name": "arch:hash", "value": h})
    return props


def _dependencies(components: Sequence[AibomComponent]) -> list[dict[str, Any]]:
    deps: list[dict[str, Any]] = []
    for comp in components:
        if comp.dependency_ids:
            deps.append({"ref": comp.entity_id, "dependsOn": list(comp.dependency_ids)})
    return deps


def required_attributes_by_specialization(schemas: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    """Convenience for callers assembling coverage input: {slug: effective_schema} →
    {slug: required attribute names}."""
    return {slug: list(schema.get("required", []) or []) for slug, schema in schemas.items()}
