"""Unit tests for _startup_schema_policy: schema-syntax, default-validity, and required-defaults policy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application._startup_schema_policy import (
    SchemaPolicyError,
    get_required_defaults_policy,
    load_repo_config,
    validate_attribute_schemata_policy,
    validate_schema_policy,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _write_schema(schemata_dir: Path, name: str, schema: dict) -> None:
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / f"attributes.{name}.schema.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )


def _write_config(arch_repo_dir: Path, policy: str) -> None:
    arch_repo_dir.mkdir(parents=True, exist_ok=True)
    (arch_repo_dir / "config.yaml").write_text(
        f"required_defaults_policy: {policy}\n", encoding="utf-8"
    )


def _make_repo_root(tmp_path: Path, *, policy: str | None = None) -> Path:
    arch_repo = tmp_path / ".arch-repo"
    arch_repo.mkdir(parents=True, exist_ok=True)
    if policy is not None:
        _write_config(arch_repo, policy)
    return tmp_path


# ── load_repo_config ──────────────────────────────────────────────────────────


def test_load_repo_config_missing_file(tmp_path: Path) -> None:
    result = load_repo_config(tmp_path)
    assert result == {}


def test_load_repo_config_reads_policy(tmp_path: Path) -> None:
    _write_config(tmp_path / ".arch-repo", "strict")
    result = load_repo_config(tmp_path)
    assert result.get("required_defaults_policy") == "strict"


# ── get_required_defaults_policy ──────────────────────────────────────────────


def test_policy_defaults_to_non_strict_when_no_config(tmp_path: Path) -> None:
    assert get_required_defaults_policy(tmp_path) == "non-strict"


def test_policy_reads_strict(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="strict")
    assert get_required_defaults_policy(root) == "strict"


def test_policy_reads_non_strict(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="non-strict")
    assert get_required_defaults_policy(root) == "non-strict"


def test_policy_unknown_value_falls_back_to_non_strict(tmp_path: Path) -> None:
    _write_config(tmp_path / ".arch-repo", "banana")
    assert get_required_defaults_policy(tmp_path) == "non-strict"


# ── validate_attribute_schemata_policy ────────────────────────────────────────


def test_no_schemata_dir_returns_empty(tmp_path: Path) -> None:
    errors, warnings = validate_attribute_schemata_policy(tmp_path)
    assert errors == []
    assert warnings == []


def test_valid_schema_with_default_is_clean(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="strict")
    schemata = root / ".arch-repo" / "schemata"
    _write_schema(schemata, "capability", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["Maturity"],
        "properties": {
            "Maturity": {
                "type": "string",
                "enum": ["Not Assessed", "Initial"],
                "default": "Not Assessed",
            }
        },
    })
    errors, warnings = validate_attribute_schemata_policy(root)
    assert errors == []
    assert warnings == []


def test_invalid_declared_default_is_hard_error(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="non-strict")
    schemata = root / ".arch-repo" / "schemata"
    _write_schema(schemata, "goal", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "Priority": {
                "type": "string",
                "enum": ["Must", "Should"],
                "default": "Cannot",   # NOT in enum — invalid default
            }
        },
    })
    errors, _ = validate_attribute_schemata_policy(root)
    assert any("Priority" in e and "default" in e for e in errors), errors


def test_invalid_default_is_error_regardless_of_policy(tmp_path: Path) -> None:
    for policy in ("strict", "non-strict"):
        root = tmp_path / policy
        root_repo = _make_repo_root(root, policy=policy)
        schemata = root_repo / ".arch-repo" / "schemata"
        _write_schema(schemata, "driver", {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["Category"],
            "properties": {
                "Category": {
                    "type": "string",
                    "enum": ["A", "B"],
                    "default": 42,   # wrong type
                }
            },
        })
        errors, _ = validate_attribute_schemata_policy(root_repo)
        assert any("Category" in e for e in errors), f"policy={policy}: {errors}"


def test_strict_required_without_default_is_hard_error(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="strict")
    schemata = root / ".arch-repo" / "schemata"
    _write_schema(schemata, "goal", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["Priority"],
        "properties": {"Priority": {"type": "string", "enum": ["Must", "Should"]}},
    })
    errors, warnings = validate_attribute_schemata_policy(root)
    assert any("Priority" in e for e in errors), errors
    assert not any("Priority" in w for w in warnings)


def test_non_strict_required_without_default_is_warning_only(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="non-strict")
    schemata = root / ".arch-repo" / "schemata"
    _write_schema(schemata, "goal", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["Priority"],
        "properties": {"Priority": {"type": "string", "enum": ["Must", "Should"]}},
    })
    errors, warnings = validate_attribute_schemata_policy(root)
    assert errors == [], errors
    assert any("Priority" in w for w in warnings), warnings


def test_invalid_json_schema_syntax_is_hard_error(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="non-strict")
    schemata = root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True, exist_ok=True)
    (schemata / "attributes.bad.schema.json").write_text("{not valid json", encoding="utf-8")
    errors, _ = validate_attribute_schemata_policy(root)
    assert any("invalid JSON" in e for e in errors), errors


# ── validate_schema_policy (cross-repo) ──────────────────────────────────────


class _StubRepo:
    def __init__(self, roots: list[Path]) -> None:
        self.repo_roots = roots


def test_validate_schema_policy_raises_on_hard_errors(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="strict")
    schemata = root / ".arch-repo" / "schemata"
    _write_schema(schemata, "goal", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["Priority"],
        "properties": {"Priority": {"type": "string"}},
    })
    repo = _StubRepo([root])
    with pytest.raises(SchemaPolicyError) as exc_info:
        validate_schema_policy(repo)  # type: ignore[arg-type]
    assert "Priority" in str(exc_info.value)


def test_validate_schema_policy_returns_warnings_for_non_strict(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="non-strict")
    schemata = root / ".arch-repo" / "schemata"
    _write_schema(schemata, "goal", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["Priority"],
        "properties": {"Priority": {"type": "string"}},
    })
    repo = _StubRepo([root])
    warnings = validate_schema_policy(repo)  # type: ignore[arg-type]
    assert any("Priority" in w for w in warnings), warnings


def test_validate_schema_policy_clean_when_all_valid(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path, policy="strict")
    schemata = root / ".arch-repo" / "schemata"
    _write_schema(schemata, "capability", {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["Maturity"],
        "properties": {
            "Maturity": {"type": "string", "enum": ["A", "B"], "default": "A"}
        },
    })
    repo = _StubRepo([root])
    warnings = validate_schema_policy(repo)  # type: ignore[arg-type]
    assert warnings == []
