"""Configurable JSON Schema loading for frontmatter and attribute validation.

Schema files are stored in ``.arch-repo/schemata/`` within a repository root.

File conventions
----------------
- ``frontmatter.{file-type}.schema.json``  — entity, outgoing, diagram
- ``attributes.{artifact-type}.schema.json`` — per entity-type base attribute schema
- ``attributes.{artifact-type}.{specialization-slug}.schema.json`` — schema attached to one
  specialization of that entity type (D13); merges into the base schema for entities
  carrying that specialization; orphaned (no matching declared specialization) is a
  verifier warning, never silently ignored.
- ``connection-metadata.{connection-type}.schema.json`` — per connection-type metadata
- ``connection-metadata.{connection-type}.{specialization-slug}.schema.json`` — schema
  attached to one specialization of that connection type; the exact mirror of the entity
  attachment above, resolved by the same order and the same named-profile bindings

Default behaviour: when no schema file exists for a given scope/type,
validation is skipped (free schema).
"""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import jsonschema  # type: ignore[import-untyped]

from src.application.profile_registry_loading import load_repo_profile_registry
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.profiles import (
    compile_profile_schema,
    merge_property_schemas,
    profile_from_inline_attributes,
)
from src.domain.ontology_representation.specializations import ConceptKind, SpecializationCatalog

SCHEMATA_DIR = ".arch-repo/schemata"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_frontmatter_schema(repo_root: Path, file_type: str) -> dict[str, Any] | None:
    """Load the frontmatter JSON Schema for *file_type* (entity, outgoing, diagram).

    Returns ``None`` when no schema file exists (free schema — skip validation).
    """
    return _load_schema_file(repo_root, f"frontmatter.{file_type}.schema.json")


def load_attribute_schema(repo_root: Path, artifact_type: str) -> dict[str, Any] | None:
    """Load the attribute JSON Schema for an entity's *artifact_type*.

    Returns ``None`` when no schema file exists (free schema — skip validation).
    """
    return _load_schema_file(repo_root, f"attributes.{artifact_type}.schema.json")


def load_connection_metadata_schema(repo_root: Path, connection_type: str) -> dict[str, Any] | None:
    """Load the metadata JSON Schema for *connection_type*.

    Returns ``None`` when no schema file exists (free schema — skip validation).
    """
    return _load_schema_file(repo_root, f"connection-metadata.{connection_type}.schema.json")


def load_specialization_attachment_schema(
    repo_root: Path, artifact_type: str, specialization_slug: str
) -> dict[str, Any] | None:
    """Load the `attributes.{artifact_type}.{specialization_slug}.schema.json` attachment file.

    Returns ``None`` when no such file exists (free schema — skip validation).
    """
    return _load_schema_file(repo_root, f"attributes.{artifact_type}.{specialization_slug}.schema.json")


def load_connection_specialization_attachment_schema(
    repo_root: Path, connection_type: str, specialization_slug: str
) -> dict[str, Any] | None:
    """Load the `connection-metadata.{connection_type}.{specialization_slug}.schema.json`
    attachment file.

    Returns ``None`` when no such file exists (free schema — skip validation).
    """
    return _load_schema_file(repo_root, f"connection-metadata.{connection_type}.{specialization_slug}.schema.json")


SchemaFileKind = Literal[
    "entity-attributes",
    "specialization-attachment",
    "connection-metadata",
    "connection-specialization-attachment",
    "frontmatter",
    "unrecognized",
]

#: The two attachment kinds, paired with the concept kind whose specializations they attach
#: to. Consumers that treat entity and connection attachments alike (orphan detection) read
#: this instead of enumerating kinds themselves.
ATTACHMENT_KINDS: dict[SchemaFileKind, ConceptKind] = {
    "specialization-attachment": "entity",
    "connection-specialization-attachment": "connection",
}


@dataclass(frozen=True)
class SchemaFileRef:
    """One classified ``.arch-repo/schemata/`` file, parsed per this module's filename
    conventions. The inventory is the single place that understands those conventions —
    consumers (startup validation, orphan detection, schema policy) filter typed records
    instead of re-parsing filenames."""

    filename: str
    kind: SchemaFileKind
    subject: str = ""  # entity type / connection type / frontmatter file-type
    specialization_slug: str = ""  # kind == "specialization-attachment" only


def _classify_schema_filename(filename: str) -> SchemaFileRef:
    suffix = ".schema.json"
    if filename.startswith("attributes.") and filename.endswith(suffix):
        parts = filename[len("attributes.") : -len(suffix)].split(".")
        if len(parts) == 1 and parts[0]:
            return SchemaFileRef(filename=filename, kind="entity-attributes", subject=parts[0])
        if len(parts) == 2 and all(parts):
            return SchemaFileRef(
                filename=filename, kind="specialization-attachment",
                subject=parts[0], specialization_slug=parts[1],
            )
        return SchemaFileRef(filename=filename, kind="unrecognized")
    if filename.startswith("connection-metadata.") and filename.endswith(suffix):
        parts = filename[len("connection-metadata.") : -len(suffix)].split(".")
        if len(parts) == 1 and parts[0]:
            return SchemaFileRef(filename=filename, kind="connection-metadata", subject=parts[0])
        if len(parts) == 2 and all(parts):
            return SchemaFileRef(
                filename=filename, kind="connection-specialization-attachment",
                subject=parts[0], specialization_slug=parts[1],
            )
        return SchemaFileRef(filename=filename, kind="unrecognized")
    if filename.startswith("frontmatter.") and filename.endswith(suffix):
        subject = filename[len("frontmatter.") : -len(suffix)]
        if subject:
            return SchemaFileRef(filename=filename, kind="frontmatter", subject=subject)
    return SchemaFileRef(filename=filename, kind="unrecognized")


def list_schema_files(repo_root: Path) -> tuple[SchemaFileRef, ...]:
    """Classified inventory of one repo's ``.arch-repo/schemata/`` directory, sorted by
    filename. Empty when the directory does not exist."""
    schemata_dir = repo_root / SCHEMATA_DIR
    if not schemata_dir.is_dir():
        return ()
    return tuple(
        _classify_schema_filename(path.name) for path in sorted(schemata_dir.glob("*.schema.json"))
    )


def compute_effective_attribute_schema(
    repo_root: Path,
    artifact_type: str,
    specialization_slugs: Sequence[str],
    *,
    specialization_catalog: SpecializationCatalog,
    profile_registry: ProfileRegistry = ProfileRegistry.empty(),
) -> tuple[dict[str, Any] | None, list[str]]:
    """Merge the base-type attribute schema with the applied specializations' contributions.

    Resolution order is deterministic (PLAN §3 P2): ``base → bound named profiles
    (declaration order) → each applied specialization's own profile (declaration order)``.
    A specialization's own profile (inline ``attributes:`` and/or its
    ``attributes.{type}.{slug}.schema.json`` attachment) is last so the specific always wins
    over a shared profile it composes. The applied set is an ordered LIST (P2a) — today an
    entity carries at most one, but the pipeline is N-specialization from the start.

    ``profile_registry`` is the shipped registry; the repo's own registry (loaded here,
    cached) overrides a shipped profile of the same name. A bound name with no definition is
    left unresolved — it is a Class-A structural error surfaced at startup (WU-Q1), never
    silently invented here. The merge itself is unchanged (already N-ary). Returns
    ``(merged_schema, conflict_messages)``; ``merged_schema`` is ``None`` only when nothing
    contributes a fragment (free schema).
    """
    return _compute_effective_schema(
        repo_root, "entity", artifact_type, specialization_slugs,
        specialization_catalog=specialization_catalog, profile_registry=profile_registry,
        load_base=load_attribute_schema, load_attachment=load_specialization_attachment_schema,
    )


def compute_effective_connection_metadata_schema(
    repo_root: Path,
    connection_type: str,
    specialization_slugs: Sequence[str],
    *,
    specialization_catalog: SpecializationCatalog,
    profile_registry: ProfileRegistry = ProfileRegistry.empty(),
) -> tuple[dict[str, Any] | None, list[str]]:
    """The connection-side mirror of :func:`compute_effective_attribute_schema`.

    Same resolution order, same named-profile bindings, same conflict reporting — a profile
    is a profile whichever concept kind binds it, so a connection specialization composes
    shared profiles exactly as an entity specialization does. Returns ``(merged_schema,
    conflict_messages)``; the schema is ``None`` only when nothing contributes a fragment.
    """
    return _compute_effective_schema(
        repo_root, "connection", connection_type, specialization_slugs,
        specialization_catalog=specialization_catalog, profile_registry=profile_registry,
        load_base=load_connection_metadata_schema,
        load_attachment=load_connection_specialization_attachment_schema,
    )


def _compute_effective_schema(
    repo_root: Path,
    concept_kind: ConceptKind,
    subject: str,
    specialization_slugs: Sequence[str],
    *,
    specialization_catalog: SpecializationCatalog,
    profile_registry: ProfileRegistry,
    load_base: Callable[[Path, str], dict[str, Any] | None],
    load_attachment: Callable[[Path, str, str], dict[str, Any] | None],
) -> tuple[dict[str, Any] | None, list[str]]:
    """The one resolution pipeline, shared by both concept kinds.

    Only the two loaders and the catalog's concept kind differ between entities and
    connections; the order, the profile de-duplication, and the merge are identical, so
    they live here once — a divergence between the two would be a defect by construction.
    """
    slugs = [slug for slug in specialization_slugs if slug]
    infos = [(slug, specialization_catalog.get(concept_kind, subject, slug)) for slug in slugs]

    fragments: list[dict[str, Any]] = []
    base = load_base(repo_root, subject)
    if base is not None:
        fragments.append(base)

    repo_registry = _repo_profile_registry(repo_root)
    seen_profiles: set[str] = set()
    for _slug, info in infos:
        if info is None:
            continue
        for name in info.bound_profiles:
            if name in seen_profiles:
                continue
            seen_profiles.add(name)
            resolved = repo_registry.get(name) or profile_registry.get(name)
            if resolved is not None:
                fragments.append(compile_profile_schema(resolved.definition))

    for slug, info in infos:
        if info is not None and info.attributes:
            fragments.append(compile_profile_schema(profile_from_inline_attributes(slug, info.attributes)))
        attachment = load_attachment(repo_root, subject, slug)
        if attachment is not None:
            fragments.append(attachment)

    if not fragments:
        return None, []
    return merge_property_schemas(fragments)


def find_orphan_attachment_schemata(repo_root: Path, specialization_catalog: SpecializationCatalog) -> list[str]:
    """Return attachment-schema filenames whose slug is not a declared specialization of
    their subject — for entity attachments (`attributes.{type}.{slug}.schema.json`) and
    connection attachments (`connection-metadata.{type}.{slug}.schema.json`) alike. An
    orphan on either side is the same mistake: a schema no loader will ever consult."""
    return [
        ref.filename
        for ref in list_schema_files(repo_root)
        if ref.kind in ATTACHMENT_KINDS
        and specialization_catalog.get(ATTACHMENT_KINDS[ref.kind], ref.subject, ref.specialization_slug) is None
    ]


#: Formats this project enforces, and what each one accepts.
#:
#: `uri` accepts a *reference*, absolute or relative, which is what the attribute is for: the value
#: points at a tracker item (`https://…`), or at an artifact this repository manages, and the latter
#: is written the way every other link to it is — `../../../model/…/REQ@….md`. JSON Schema's own
#: `uri` format requires a scheme and would refuse exactly the case the facet exists to carry;
#: `uri-reference` is the correct reading and is what this checks.
#:
#: Checked here rather than through `jsonschema`'s format machinery, which is annotation-only unless
#: a checker is installed and which would otherwise add a dependency to answer a question this
#: narrow.
#: `date` is a calendar date, `YYYY-MM-DD`, per RFC 3339 full-date — the shape a review date, a
#: baseline date or a decision date is written in everywhere else in this project.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_FORMAT_CHECKS: dict[str, Callable[[str], bool]] = {
    "uri": lambda value: bool(value.strip()) and not any(c.isspace() for c in value.strip()),
    "date": lambda value: _valid_iso_date(value.strip()),
}


def _valid_iso_date(value: str) -> bool:
    if _ISO_DATE.match(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


#: The formats a declaration may name. Startup refuses any other, because a format nothing checks
#: would compile into the schema and be enforced by nothing — see `_startup_schema_policy`.
ENFORCED_FORMATS: frozenset[str] = frozenset(_FORMAT_CHECKS)


def _format_errors(instance: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Every property whose value does not satisfy the `format` its schema declares."""
    properties: dict[str, Any] = schema.get("properties") or {}
    errors: list[str] = []
    for name, prop_schema in properties.items():
        check = _FORMAT_CHECKS.get(str((prop_schema or {}).get("format") or ""))
        value = instance.get(name)
        if check is None or not isinstance(value, str) or not value:
            continue
        if not check(value):
            declared = prop_schema["format"]
            errors.append(f"{name}: {value!r} is not a valid {declared}")
    return errors


def validate_against_schema(instance: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate *instance* against *schema*, returning a list of error messages.

    Returns an empty list when *instance* conforms to *schema*.

    `format` is enforced here rather than left as an annotation. A facet the decoder honours and the
    validator drops is a silent weakening — the same shape as a notation honoured by one loader of
    four — so a declared format is checked wherever a schema reaches this function, which is every
    frontmatter, Properties-table and metadata read in the verifier.
    """
    validator_cls = jsonschema.Draft202012Validator
    validator = validator_cls(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
        errors.append(f"{path}: {error.message}")
    errors.extend(_format_errors(instance, schema))
    return errors


def schema_required_properties(schema: dict[str, Any]) -> list[str]:
    """Return the list of required property names from a schema."""
    return list(schema.get("required", []))


def schema_all_properties(schema: dict[str, Any]) -> list[str]:
    """Return all declared property names from a schema."""
    return list(schema.get("properties", {}).keys())


_CONSTRAINT_KEYS = (
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "pattern",
)


def attribute_descriptors(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-attribute UI descriptors (type, format, enum, default, constraints) from a JSON Schema.

    One shape for every authoring surface — the entity schema endpoint and the connection
    metadata guidance both serve it, so one typed input component can render either without
    knowing which side it came from.
    """
    props: dict[str, Any] = schema.get("properties", {}) or {}
    out: dict[str, dict[str, Any]] = {}
    for name, prop_schema in props.items():
        if not isinstance(prop_schema, dict):
            continue
        descriptor: dict[str, Any] = {"type": prop_schema.get("type", "string")}
        # What the value addresses, where it addresses something. An authoring input renders a
        # `uri` attribute as a reference rather than as free text, and the descriptor is the only
        # thing it sees — a facet that stops here is a facet the form cannot honour.
        if prop_schema.get("format"):
            descriptor["format"] = str(prop_schema["format"])
        if "enum" in prop_schema:
            descriptor["enum"] = [str(v) for v in prop_schema["enum"]]
        if "default" in prop_schema:
            raw = prop_schema["default"]
            if isinstance(raw, bool):
                descriptor["default"] = "true" if raw else "false"
            elif raw is not None:
                descriptor["default"] = str(raw)
        constraints = {key: prop_schema[key] for key in _CONSTRAINT_KEYS if key in prop_schema}
        if constraints:
            descriptor["constraints"] = constraints
        # An array's item schema, so a list editor can type each element rather than falling
        # back to a free-text JSON box. Kept to the fields a per-item input needs.
        item_schema = prop_schema.get("items")
        if descriptor["type"] == "array" and isinstance(item_schema, dict):
            item: dict[str, Any] = {"type": item_schema.get("type", "string")}
            if "enum" in item_schema:
                item["enum"] = [str(v) for v in item_schema["enum"]]
            item_constraints = {key: item_schema[key] for key in _CONSTRAINT_KEYS if key in item_schema}
            if item_constraints:
                item["constraints"] = item_constraints
            descriptor["items"] = item
        out[name] = descriptor
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


@lru_cache(maxsize=128)
def _load_schema_file(repo_root: Path, filename: str) -> dict[str, Any] | None:
    schema_path = repo_root / SCHEMATA_DIR / filename
    if not schema_path.is_file():
        return None
    with open(schema_path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=32)
def _repo_profile_registry(repo_root: Path) -> ProfileRegistry:
    """The repo's optional named-profile registry, cached per root — schema resolution reads
    it once per (type, specialization) pair otherwise, so caching keeps the hot path cheap."""
    return load_repo_profile_registry(repo_root)


def clear_schema_cache() -> None:
    """Clear the in-memory schema caches (useful in tests)."""
    _load_schema_file.cache_clear()
    _repo_profile_registry.cache_clear()
