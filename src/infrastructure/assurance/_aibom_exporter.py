"""AI-BOM export and reconcile — CycloneDX 1.6 ML-BOM/ASBOM.

build_cyclonedx_16() emits a CycloneDX 1.6-flavoured JSON document from a
list of AI-component dicts (sourced from architecture entities with the
ai-component attribute profile applied).

reconcile_aibom() diffs a modeled list against a discovered list and returns
a drift report: added (in discovered, not modeled), removed (modeled, not
discovered), and matched components.

Component dict keys used by this module (all optional except name):
  name, purl, cpe, ai_role, version, provider, hosted, external,
  model_card_ref, dataset_provenance, component_type, arch_entity_id
"""

from __future__ import annotations

import hashlib
import uuid

from src.domain.clock import utc_now_iso

_CDX_AI_ROLE_TO_TYPE: dict[str, str] = {
    "machine-learning-model": "machine-learning-model",
    "dataset": "data",
    "inference-service": "service",
    "mcp-server": "service",
    "tool": "library",
    "agent": "application",
    "orchestrator": "application",
    "prompt": "data",
    "guardrail": "library",
    "vector-store": "data",
    "rag-pipeline": "application",
}

# Canonical AI-BOM role vocabulary — single source of truth. Surfaced over HTTP
# (GET /api/assurance/aibom/roles) so the GUI never redeclares the enum.
AI_BOM_ROLES: tuple[str, ...] = tuple(_CDX_AI_ROLE_TO_TYPE)


# Optional CycloneDX node fields copied verbatim (source key, node key).
_CDX_NODE_FIELDS: tuple[tuple[str, str], ...] = (("version", "version"), ("purl", "purl"), ("cpe", "cpe"))
# Optional ai:/arch: properties emitted from present component fields (source key, property name).
_CDX_PROP_FIELDS: tuple[tuple[str, str], ...] = (
    ("ai_role", "ai:role"),
    ("provider", "ai:provider"),
    ("hosted", "ai:hosted"),
    ("external", "ai:external"),
    ("arch_entity_id", "arch:entity_id"),
)


def _cdx_component(comp: dict[str, object]) -> dict[str, object]:
    ai_role = str(comp.get("ai_role") or "")
    node: dict[str, object] = {
        "type": _CDX_AI_ROLE_TO_TYPE.get(ai_role, "library"),
        "name": str(comp.get("name") or ""),
        **{dst: str(comp[src]) for src, dst in _CDX_NODE_FIELDS if comp.get(src)},
    }
    if comp.get("model_card_ref"):
        node["modelCard"] = {"bom-ref": str(comp["model_card_ref"])}
    props = [{"name": label, "value": str(comp[src])} for src, label in _CDX_PROP_FIELDS if comp.get(src)]
    if props:
        node["properties"] = props
    return node


def build_cyclonedx_16(
    ai_components: list[dict[str, object]],
    *,
    serial: str | None = None,
    notes: str = "",
) -> dict[str, object]:
    """Emit a CycloneDX 1.6 ML-BOM/ASBOM JSON document."""
    bom_serial = serial or f"urn:uuid:{uuid.uuid4()}"
    timestamp = utc_now_iso()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": bom_serial,
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": [{"name": "arch-assurance", "version": "1.0"}],
            "notes": notes,
        },
        "components": [_cdx_component(c) for c in ai_components],
    }


def _component_key(comp: dict[str, object]) -> str:
    """Stable identity key for reconciliation: purl if present, else name."""
    purl = str(comp.get("purl") or "")
    if purl:
        return purl
    return "name:" + hashlib.sha256(str(comp.get("name") or "").encode()).hexdigest()[:8]


def reconcile_aibom(
    modeled: list[dict[str, object]],
    discovered: list[dict[str, object]],
) -> dict[str, object]:
    """Diff a modeled AI-BOM against a discovered one.

    Returns a drift report with added, removed, and matched component lists.
    """
    modeled_keys = {_component_key(c): c for c in modeled}
    discovered_keys = {_component_key(c): c for c in discovered}

    added = [discovered_keys[k] for k in discovered_keys if k not in modeled_keys]
    removed = [modeled_keys[k] for k in modeled_keys if k not in discovered_keys]
    matched_keys = set(modeled_keys) & set(discovered_keys)
    matched = [
        {
            "key": k,
            "modeled": modeled_keys[k],
            "discovered": discovered_keys[k],
        }
        for k in matched_keys
    ]

    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "matched_count": len(matched),
        "added": added,
        "removed": removed,
        "matched": matched,
        "summary": (
            f"{len(added)} component(s) in discovered but not modeled; "
            f"{len(removed)} modeled but not in discovered; "
            f"{len(matched)} matched."
        ),
    }
