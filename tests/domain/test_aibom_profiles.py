"""WU-A2: the AIBOM shared profiles and per-specialization attributes.

The module ships the shared `ai-supplier` / `ai-licensing` profiles (profiles.yaml) and binds
them from the AI specializations, plus the model card inline on `ai-model`. Base-type
attributes are inherited, never redeclared (D3a). These are executable checks against the
real archimate-4 module + resolver.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifacts.schema import clear_schema_cache, compute_effective_attribute_schema
from src.domain.repository.repo_default_attribute_schemata import ARCHIMATE_ATTRIBUTE_SCHEMATA
from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs


def _catalogs():
    return build_runtime_catalogs(build_module_registry())


def _scaffold_base_schemata(repo_root: Path) -> None:
    """Write the shipped default attribute schemata a scaffolded/upgraded repo carries, so
    base-type inheritance is exercised the way it works in a real repo."""
    schemata = repo_root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True, exist_ok=True)
    for filename, schema in ARCHIMATE_ATTRIBUTE_SCHEMATA.items():
        (schemata / filename).write_text(json.dumps(schema), encoding="utf-8")
    clear_schema_cache()


def test_shared_profiles_load_as_valid_schema(tmp_path: Path) -> None:
    c = _catalogs()
    assert c.profiles.get("ai-supplier") is not None
    assert c.profiles.get("ai-licensing") is not None
    # Compiling the profile into a JSON-Schema fragment must not raise.
    from src.domain.ontology_representation.profiles import compile_profile_schema

    frag = compile_profile_schema(c.profiles.get("ai-supplier").definition)
    assert "Supplier" in frag["properties"]


def test_ai_model_effective_schema_merges_base_shared_and_modelcard(tmp_path: Path) -> None:
    _scaffold_base_schemata(tmp_path)
    c = _catalogs()
    schema, conflicts = compute_effective_attribute_schema(
        tmp_path, "application-component", ["ai-model"],
        specialization_catalog=c.specializations, profile_registry=c.profiles,
    )
    assert conflicts == []
    props = set(schema["properties"])
    assert {"Supplier", "Publisher", "Licenses", "Hashes"} <= props  # shared profiles
    assert {"Approach", "Task", "Performance Metrics", "Ethical Considerations"} <= props  # model card


def test_ai_dataset_inherits_base_data_object_attributes_without_redeclaring(tmp_path: Path) -> None:
    # D3a: the AIBOM's classification/sensitiveData derive from the base data-object
    # Sensitivity, which the profile does NOT redeclare — inheritance delivers it.
    _scaffold_base_schemata(tmp_path)
    c = _catalogs()
    schema, conflicts = compute_effective_attribute_schema(
        tmp_path, "data-object", ["ai-dataset"],
        specialization_catalog=c.specializations, profile_registry=c.profiles,
    )
    assert conflicts == []
    props = set(schema["properties"])
    assert {"Sensitivity", "Provenance"} <= props  # inherited from the data-object base
    assert "Dataset Role" in props  # the dataset's own attribute
    assert {"Supplier", "Licenses"} <= props  # shared profiles


def test_no_orphan_ai_attachment_schemata(tmp_path: Path) -> None:
    # AIBOM attributes live in the module (profiles.yaml + inline), NOT in per-repo
    # attachment files, so there are no `attributes.<type>.<ai-slug>.schema.json` shipped
    # defaults to orphan. The default set ships none.
    ai_attachments = [
        name for name in ARCHIMATE_ATTRIBUTE_SCHEMATA
        if name.startswith("attributes.") and name.count(".") >= 3 and "ai-" in name
    ]
    assert ai_attachments == []
