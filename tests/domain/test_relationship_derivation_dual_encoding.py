"""Independent transcription checks for relationship-derivation metadata."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from src.ontologies.archimate_4 import module
from tests.fixtures.viewpoints.derivation_rules_independent_encoding import COMPOSITION_RULES, RESTRICTIONS

_FIXTURE = Path(__file__).parents[1] / "fixtures/viewpoints/derivation_rules_independent_encoding.py"


def _composition_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "spec_ref": row["spec_ref"],
        "certainty": row["certainty"],
        "first_role": row["first_role"],
        "second_role": row["second_role"],
        "result": row["result"],
        "join": row.get("join", "target-source"),
        "result_source": row.get("result_source", "first-source"),
        "result_target": row.get("result_target", "second-target"),
        "first_artifact_type": row.get("first_artifact_type"),
        "second_artifact_type": row.get("second_artifact_type"),
        "second_artifact_types": row.get("second_artifact_types", ()),
        "intermediate_artifact_type": row.get("intermediate_artifact_type"),
        "requires_permitted_result": row.get("requires_permitted_result", False),
    }


def _restriction_row(row: Mapping[str, object]) -> dict[str, object]:
    defaults: dict[str, object] = {
        "source_domains": frozenset(),
        "target_domains": frozenset(),
        "target_domains_excluded": frozenset(),
        "source_artifact_types": frozenset(),
        "source_artifact_types_excluded": frozenset(),
        "intermediate_artifact_types": frozenset(),
        "source_passive": None,
        "target_passive": None,
        "connection_artifact_types": frozenset(),
        "allowed_connection_artifact_types": frozenset(),
        "intermediate_domain_must_match_endpoint": False,
        "intermediate_domain_exception": False,
        "always_disallow": False,
    }
    values = {
        name: _string_set(row, name) if isinstance(default, frozenset) else row.get(name, default)
        for name, default in defaults.items()
    }
    return {
        "spec_ref": row["spec_ref"],
        **values,
    }


def _string_set(row: Mapping[str, object], name: str) -> frozenset[object]:
    value = row.get(name, ())
    assert isinstance(value, tuple)
    return frozenset(value)


def test_independent_fixture_has_no_derivation_module_imports() -> None:
    tree = ast.parse(_FIXTURE.read_text(encoding="utf-8"))

    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and "relationship_derivation" in ast.unparse(node)
    ]


def test_runtime_composition_rules_match_the_independent_transcription() -> None:
    assert tuple(_composition_row(row) for row in COMPOSITION_RULES) == tuple(
        asdict(rule) for rule in module.derivation_rules
    )


def test_runtime_restrictions_match_the_independent_transcription() -> None:
    assert tuple(_restriction_row(row) for row in RESTRICTIONS) == tuple(
        asdict(rule) for rule in module.derivation_restrictions
    )
