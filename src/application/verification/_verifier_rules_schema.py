"""JSON Schema and attribute validation rules."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.application.artifacts.schema import (
    compute_effective_attribute_schema,
    compute_effective_connection_metadata_schema,
    load_frontmatter_schema,
    validate_against_schema,
)
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.property_value import decode_lenient, get_adhoc_type
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.domain.repository.properties_section import read_properties

# ---------------------------------------------------------------------------
# Configurable JSON Schema checks (WS-C)
# ---------------------------------------------------------------------------


def check_frontmatter_schema(
    fm: dict,
    repo_root: Path,
    file_type: str,
    result: VerificationResult,
    loc: str,
) -> None:
    """Validate frontmatter dict against the repo's JSON Schema for *file_type*.

    If no schema file exists for the file type, validation is silently skipped
    (free schema).  Schema errors are reported as warnings (W041) rather than
    hard errors so that repos can adopt schemas incrementally.
    """
    schema = load_frontmatter_schema(repo_root, file_type)
    if schema is None:
        return
    errors = validate_against_schema(fm, schema)
    for msg in errors:
        result.issues.append(
            Issue(
                Severity.WARNING,
                "W041",
                f"Frontmatter schema ({file_type}): {msg}",
                loc,
            )
        )


def check_attribute_schema(
    content: str,
    fm: dict,
    repo_root: Path,
    result: VerificationResult,
    loc: str,
    *,
    specialization_catalog: SpecializationCatalog | None = None,
    profile_registry: ProfileRegistry | None = None,
) -> None:
    """Validate Properties table attributes against the effective per-type attribute schema.

    Extracts key-value pairs from the ``## Properties`` markdown table and validates them
    against the base-type schema (``attributes.{artifact-type}.schema.json``) merged with
    the entity's own specialization's profile, if any (D13) — see
    ``compute_effective_attribute_schema``. A property redefined incompatibly between the
    base schema and the specialization's contribution is a blocking E043 error.

    Cells are decoded using the schema's declared type (schema-driven decode).
    Decode failures produce a blocking E042 error; other constraint violations
    remain W042 warnings until schemas are fully remediated.
    """
    artifact_type = fm.get("artifact-type", "")
    if not artifact_type:
        return
    schema, conflicts = compute_effective_attribute_schema(
        repo_root,
        str(artifact_type),
        [str(fm.get("specialization", "") or "")],
        specialization_catalog=specialization_catalog or SpecializationCatalog.empty(),
        profile_registry=profile_registry or ProfileRegistry.empty(),
    )
    for msg in conflicts:
        result.issues.append(Issue(Severity.ERROR, "E043", f"Attribute schema ({artifact_type}): {msg}", loc))
    if schema is None:
        return
    props = stated_properties(content)
    if props is None:
        required = schema.get("required", [])
        if required:
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W042",
                    (f"Attribute schema ({artifact_type}): no Properties table found but schema requires: {required}"),
                    loc,
                )
            )
        return

    attribute_types: dict[str, str] = fm.get("attribute-types", {}) or {}
    result.issues.extend(
        stated_property_issues(
            props, schema, artifact_type=str(artifact_type), attribute_types=attribute_types, loc=loc
        )
    )


def stated_property_issues(
    props: Mapping[str, str],
    schema: Mapping[str, Any],
    *,
    artifact_type: str,
    attribute_types: Mapping[str, str],
    loc: str,
) -> list[Issue]:
    """What an attribute schema says about the property cells an entity states.

    The value checks of `check_attribute_schema`, apart from where the cells came from — so
    something that is not yet an entity file can ask what the write of one would be told. A
    scratchpad note about to be lifted does: it holds the same properties, and the answer it is
    shown has to be the one the entity write gives.

    Cells are decoded by the schema's declared type. A cell that cannot be decoded is a blocking
    E042; every other constraint violation is a W042 warning until schemas are fully remediated.
    """
    issues: list[Issue] = []
    # Schema-driven decode: convert raw cell strings to typed values before
    # running jsonschema.  This makes type: integer / boolean / number work
    # correctly and detects genuinely wrong values (E042 = blocking).
    prop_schemata: dict[str, Any] = schema.get("properties", {}) or {}
    decoded: dict[str, Any] = {}
    for key, cell in props.items():
        prop_schema = prop_schemata.get(key)
        if prop_schema:
            value, err = decode_lenient(cell, prop_schema)
        else:
            adhoc_type = get_adhoc_type(key, dict(attribute_types))
            value, err = decode_lenient(cell, {"type": adhoc_type})
        if err:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "E042",
                    f"Attribute schema ({artifact_type}): type error on '{key}': {err}",
                    loc,
                )
            )
        decoded[key] = value

    for msg in validate_against_schema(decoded, dict(schema)):
        issues.append(
            Issue(
                Severity.WARNING,
                "W042",
                f"Attribute schema ({artifact_type}): {msg}",
                loc,
            )
        )

    missing_recommended = [name for name in schema.get("x-recommended", []) if name not in decoded]
    if missing_recommended:
        issues.append(
            Issue(
                Severity.WARNING,
                "W042",
                f"Attribute schema ({artifact_type}): missing recommended attribute(s): {missing_recommended}",
                loc,
            )
        )
    return issues


def check_connection_metadata_schema(
    metadata: dict[str, Any],
    connection_type: str,
    repo_root: Path,
    result: VerificationResult,
    loc: str,
    *,
    specialization_catalog: SpecializationCatalog | None = None,
    profile_registry: ProfileRegistry | None = None,
) -> None:
    """Validate a connection's per-connection metadata block against the EFFECTIVE schema
    for its ``(connection-type, specialization)`` pair — the base
    ``connection-metadata.{connection-type}.schema.json`` merged with the connection's own
    specialization contribution and its bound named profiles.

    The entity mirror of this is ``check_attribute_schema``: a property redefined
    incompatibly across those fragments is a blocking E045 error (E043's connection
    counterpart), because the pair then has no unambiguous schema to validate against at
    all. Instance violations stay W043 warnings, as before. If nothing declares a fragment,
    validation is silently skipped (free schema).
    """
    specialization = str(metadata.get("specialization", "") or "")
    schema, conflicts = compute_effective_connection_metadata_schema(
        repo_root,
        connection_type,
        [specialization],
        specialization_catalog=specialization_catalog or SpecializationCatalog.empty(),
        profile_registry=profile_registry or ProfileRegistry.empty(),
    )
    for msg in conflicts:
        result.issues.append(
            Issue(Severity.ERROR, "E045", f"Connection metadata schema ({connection_type}): {msg}", loc)
        )
    if schema is None:
        return
    for msg in validate_against_schema(metadata, schema):
        result.issues.append(
            Issue(
                Severity.WARNING,
                "W043",
                f"Connection metadata schema ({connection_type}): {msg}",
                loc,
            )
        )


def stated_properties(content: str) -> dict[str, str] | None:
    """The attributes the ``## Properties`` table gives a value, or ``None`` without such a section.

    An attribute whose cell is empty is the scaffold row the writer leaves for a schema key nobody
    has filled in. The table states it; the entity does not, so no rule here is asked about it.
    """
    properties = read_properties(content)
    if properties is None:
        return None
    return {name: cell for name, cell in properties.items() if name and cell}


# ---------------------------------------------------------------------------
# Module source-path existence check (W160)
# ---------------------------------------------------------------------------


def _find_source_root(path: Path) -> Path | None:
    """Return the first ancestor of *path* that contains a ``src/`` subdirectory."""
    for parent in path.parents:
        if (parent / "src").is_dir():
            return parent
    return None


def check_module_source_path(
    content: str,
    file_path: Path,
    result: VerificationResult,
    loc: str,
) -> None:
    """Warn (W160) when a ``Module:`` property in the Properties table points at a
    source path that does not exist on disk.

    Silently skips when the entity has no ``Module:`` property, or when no
    ancestor directory containing ``src/`` can be found (the architecture repo
    is not co-located with the source tree).
    """
    props = stated_properties(content)
    if not props:
        return
    module_val = props.get("Module", "").strip()
    if not module_val:
        return
    source_root = _find_source_root(file_path)
    if source_root is None:
        return
    if not (source_root / module_val).exists():
        result.issues.append(
            Issue(
                Severity.WARNING,
                "W160",
                f"Module property references non-existent source path: '{module_val}'",
                loc,
            )
        )


# ---------------------------------------------------------------------------
