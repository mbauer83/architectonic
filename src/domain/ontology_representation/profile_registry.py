"""Named attribute-profile registry — reusable, opt-in profiles bound by specializations.

Distinct from a specialization's own 1:1 profile (``profiles.py``): a NAMED profile is a
reusable attribute set that several ``(entity-type, specialization)`` pairs may bind by name,
so a shared attribute set is authored once and applied in several places. The registry
carries two independent version tags (PLAN §3 P4), each with a distinct job:

* ``profile_schema`` on the registry file — the *declaration-format* version, a migration
  hook. An unrecognised value is a TYPED ERROR, never a best-effort parse (mirrors the
  ``QUERY_SCHEMA_VERSION`` guard).
* ``version`` on each named profile — the *content* version, so reconciliation can tell
  "your file differs from the shipped default" apart from "the shipped profile advanced to
  v3 while your customisation is based on v1".

This module is the FORMAT and the in-memory model only. Binding a specialization to a
profile (Stream P2) and folding bound profiles into the effective schema (Stream P3) are
separate; nothing here resolves or merges attributes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from src.domain.ontology_representation.profiles import ProfileDefinition, attributes_from_mapping

PROFILE_SCHEMA_VERSION = 1

ConflictClass = Literal["structural", "scoped"]


class ProfileRegistryError(ValueError):
    """A registry file is structurally untrustworthy (Class A): unparseable, an unknown
    format version, or a malformed profile declaration. The ``label`` names the source so a
    startup/CLI caller can point at the offending file."""

    def __init__(self, message: str, *, label: str) -> None:
        super().__init__(f"{label}: {message}")
        self.label = label


@dataclass(frozen=True)
class NamedProfile:
    """One reusable profile: an identifying ``name``, a content ``version``, and the
    compiled attribute set (reusing the ``profiles.py`` model so a named profile's attributes
    parse and compile identically to an inline specialization profile)."""

    name: str
    version: int
    definition: ProfileDefinition


@dataclass(frozen=True)
class ProfileRegistry:
    """An immutable set of named profiles, unique by name. ``profile_schema`` is the file's
    declaration-format version; an empty registry is the valid "no named profiles" state
    every existing repository is in."""

    profile_schema: int = PROFILE_SCHEMA_VERSION
    profiles: Mapping[str, NamedProfile] = field(default_factory=lambda: MappingProxyType({}))

    @staticmethod
    def empty() -> "ProfileRegistry":
        return ProfileRegistry(profile_schema=PROFILE_SCHEMA_VERSION, profiles=MappingProxyType({}))

    def get(self, name: str) -> NamedProfile | None:
        return self.profiles.get(name)

    def overlay(self, other: "ProfileRegistry") -> "ProfileRegistry":
        """The effective registry when *other* (a repo-level registry) may OVERRIDE this
        (shipped) one by name — the resolution-layer override P3 alludes to, distinct from
        the collision-rejecting cross-module ``merge_profile_registries``."""
        return ProfileRegistry(PROFILE_SCHEMA_VERSION, MappingProxyType({**self.profiles, **other.profiles}))


def merge_profile_registries(registries: Iterable[ProfileRegistry]) -> ProfileRegistry:
    """Union several registries' profiles. Names are a single global namespace, so a
    collision between two SHIPPED module registries is a bug and raises — the same
    uniqueness discipline ``SpecializationCatalog`` enforces. Repo-level override of a
    shipped profile is a resolution-layer concern (Stream P3), never a silent merge here."""
    merged: dict[str, NamedProfile] = {}
    for registry in registries:
        for name, profile in registry.profiles.items():
            if name in merged:
                raise ProfileRegistryError(
                    f"named profile {name!r} is defined more than once", label="<registry merge>"
                )
            merged[name] = profile
    return ProfileRegistry(profile_schema=PROFILE_SCHEMA_VERSION, profiles=MappingProxyType(merged))


@dataclass(frozen=True)
class ProfileConflict:
    """One classified conflict from resolving a (entity-type, specialization) pair, tagged
    by blast radius (PLAN §4). ``structural`` = Class A; ``scoped`` = Class B."""

    conflict_class: ConflictClass
    message: str


def classify_profile_conflicts(
    bound_profile_names: Iterable[str],
    registry: ProfileRegistry,
    merge_conflicts: Iterable[str],
) -> tuple[ProfileConflict, ...]:
    """Classify the conflicts a (entity-type, specialization) resolution surfaces, by blast
    radius (PLAN §4):

    * STRUCTURAL (Class A) — a binding names a profile the registry does not define; the
      effective schema cannot even be determined, so nothing downstream is trustworthy.
    * SCOPED (Class B) — an incompatible-type redefinition confined to this pair; the rest
      of the model is well-defined.

    Identical redefinition composes silently (PLAN §3 P3), so it never produces a merge
    conflict and never appears here. ``registry`` must be the EFFECTIVE registry (shipped
    overlaid by repo) so a repo-defined profile is not misreported as undefined."""
    conflicts: list[ProfileConflict] = [
        ProfileConflict("structural", f"binding references undefined named profile {name!r}")
        for name in bound_profile_names
        if registry.get(name) is None
    ]
    conflicts.extend(ProfileConflict("scoped", message) for message in merge_conflicts)
    return tuple(conflicts)


def unresolved_profile_bindings(
    bindings: Iterable[tuple[str, Sequence[str]]], registry: ProfileRegistry
) -> tuple[str, ...]:
    """Structural (Class A) findings: every ``(label, bound_names)`` binding naming a profile
    the effective registry does not define. Pure — the caller supplies the labelled bindings
    (typically one per specialization) and the effective (shipped ∪ repo) registry."""
    return tuple(
        f"{label} binds undefined named profile {name!r}"
        for label, names in bindings
        for name in names
        if registry.get(name) is None
    )


def profile_registry_from_mapping(raw: object, *, label: str) -> ProfileRegistry:
    """Parse a registry mapping. Enforces the ``profile_schema`` guard and per-profile
    ``version``; any structural defect raises ``ProfileRegistryError`` (Class A)."""
    if not isinstance(raw, Mapping):
        raise ProfileRegistryError("registry must be a mapping", label=label)
    if "profile_schema" not in raw:
        raise ProfileRegistryError("'profile_schema' is required", label=label)
    schema_version = _require_int(raw["profile_schema"], "profile_schema", label=label)
    if schema_version != PROFILE_SCHEMA_VERSION:
        raise ProfileRegistryError(
            f"unsupported profile_schema {schema_version!r}, expected {PROFILE_SCHEMA_VERSION}", label=label
        )
    raw_profiles: object = raw.get("profiles") or {}
    if not isinstance(raw_profiles, Mapping):
        raise ProfileRegistryError("'profiles' must be a mapping of name to profile", label=label)
    profiles: dict[str, NamedProfile] = {}
    for name, body in raw_profiles.items():
        profiles[str(name)] = _named_profile_from_mapping(str(name), body, label=label)
    return ProfileRegistry(profile_schema=schema_version, profiles=MappingProxyType(profiles))


def _named_profile_from_mapping(name: str, body: object, *, label: str) -> NamedProfile:
    if not isinstance(body, Mapping):
        raise ProfileRegistryError(f"profile {name!r} must be a mapping", label=label)
    if "version" not in body:
        raise ProfileRegistryError(f"profile {name!r} is missing 'version'", label=label)
    version = _require_int(body["version"], f"profile {name!r} version", label=label)
    raw_attributes: object = body.get("attributes") or {}
    if not isinstance(raw_attributes, Mapping):
        raise ProfileRegistryError(f"profile {name!r} 'attributes' must be a mapping", label=label)
    definition = ProfileDefinition(slug=name, name=name, attributes=attributes_from_mapping(raw_attributes))
    return NamedProfile(name=name, version=version, definition=definition)


def _require_int(value: object, what: str, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileRegistryError(f"{what} must be an integer, got {value!r}", label=label)
    return value
