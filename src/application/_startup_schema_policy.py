"""Startup validation: attribute-schema syntax, declared formats, declared-default validity, and the
required-defaults policy.

Per-repo ``required_defaults_policy`` (from ``.arch-repo/config.yaml``) controls whether
required properties without a declared ``default`` are a hard error (``strict``) or a
finding (``non-strict``). Invalid JSON Schema syntax and declared defaults that do not
validate against their own property schema are always hard errors regardless of policy. So is a
``format`` this project does not enforce: the facet says a value *addresses* something, and one that
no checker recognises would compile into the schema, reach an authoring form and be validated by
nothing — the silent weakening the facet exists to rule out. Refusing it here is the one place that
sees a declaration before anything reads it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema

from src.application.artifacts.schema import ENFORCED_FORMATS, list_schema_files
from src.domain.yaml_documents import parse_yaml

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository

_ARCH_REPO_DIR = ".arch-repo"
_SCHEMATA_SUBDIR = "schemata"
_CONFIG_FILE = _ARCH_REPO_DIR + "/config.yaml"
_POLICY_KEY = "required_defaults_policy"
_STRICT = "strict"
_NON_STRICT = "non-strict"
_VALID_POLICIES = frozenset({_STRICT, _NON_STRICT})


# ── Public error class ────────────────────────────────────────────────────────


class SchemaPolicyError(Exception):
    """Raised when attribute-schema policy validation finds hard failures."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("\n".join(errors))


# ── Config loading ────────────────────────────────────────────────────────────


def load_repo_config(repo_root: Path) -> dict[str, Any]:
    """Load ``.arch-repo/config.yaml``; return ``{}`` when missing or empty."""
    config_path = repo_root / _CONFIG_FILE
    if not config_path.is_file():
        return {}
    with open(config_path, encoding="utf-8") as fh:
        data = parse_yaml(fh)
    return data if isinstance(data, dict) else {}


def get_required_defaults_policy(repo_root: Path) -> str:
    """Return ``'strict'`` or ``'non-strict'`` for this repo (default ``'non-strict'``)."""
    config = load_repo_config(repo_root)
    policy = config.get(_POLICY_KEY, _NON_STRICT)
    return str(policy) if policy in _VALID_POLICIES else _NON_STRICT


# ── Per-file validation ───────────────────────────────────────────────────────


def _validate_one_schema_file(
    schema_path: Path, policy: str
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    label = schema_path.name

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: invalid JSON — {exc}")
        return errors, warnings

    if not isinstance(schema, dict):
        errors.append(f"{label}: schema root must be a JSON object")
        return errors, warnings

    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.exceptions.SchemaError as exc:
        errors.append(f"{label}: invalid JSON Schema — {exc.message}")
        return errors, warnings

    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = schema.get("required", [])

    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            continue
        declared_format = str(prop_schema.get("format") or "")
        if declared_format and declared_format not in ENFORCED_FORMATS:
            known = ", ".join(sorted(ENFORCED_FORMATS))
            errors.append(
                f"{label}: property {prop_name!r} declares format {declared_format!r}, which "
                f"nothing enforces — declare one of: {known}"
            )
        if "default" not in prop_schema:
            continue
        try:
            jsonschema.Draft202012Validator(prop_schema).validate(prop_schema["default"])
        except jsonschema.ValidationError as exc:
            errors.append(
                f"{label}: declared default for {prop_name!r} does not validate "
                f"against its own schema — {exc.message}"
            )

    for prop_name in required:
        prop_schema = properties.get(prop_name)
        if not isinstance(prop_schema, dict) or "default" not in prop_schema:
            msg = (
                f"{label}: required property {prop_name!r} has no declared default "
                f"(required_defaults_policy={policy!r})"
            )
            if policy == _STRICT:
                errors.append(msg)
            else:
                warnings.append(msg)

    return errors, warnings


# ── Repo-level aggregator ─────────────────────────────────────────────────────


def validate_attribute_schemata_policy(
    repo_root: Path,
) -> tuple[list[str], list[str]]:
    """Validate all ``attributes.*.schema.json`` files under *repo_root*.

    Returns ``(errors, warnings)``. Errors are always fatal; warnings are findings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    schemata_dir = repo_root / _ARCH_REPO_DIR / _SCHEMATA_SUBDIR
    if not schemata_dir.is_dir():
        return errors, warnings

    policy = get_required_defaults_policy(repo_root)
    attribute_kinds = ("entity-attributes", "specialization-attachment")
    for ref in list_schema_files(repo_root):
        if ref.kind not in attribute_kinds:
            continue
        errs, warns = _validate_one_schema_file(schemata_dir / ref.filename, policy)
        errors.extend(errs)
        warnings.extend(warns)
    return errors, warnings


# ── Cross-repo entry point ────────────────────────────────────────────────────


def validate_schema_policy(repo: "ArtifactRepository") -> list[str]:
    """Validate attribute-schema policy across all repo roots.

    Raises :exc:`SchemaPolicyError` on hard failures; returns warnings.
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []
    for repo_root in repo.repo_roots:
        errs, warns = validate_attribute_schemata_policy(repo_root)
        all_errors.extend(errs)
        all_warnings.extend(warns)
    if all_errors:
        raise SchemaPolicyError(all_errors)
    return all_warnings
