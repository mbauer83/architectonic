"""Class B quarantine (PLAN §4): a ``(type, specialization)`` pair whose bound profiles
conflict with each other or the base schema on an attribute's type. The rest of the model
stays well-defined, so the failure is confined to the pair — reads continue, but a
create/edit for that pair is rejected at the write boundary (WU-Q3).

Both concept kinds are covered by the same machinery: an entity type with its attribute
schema, and a connection type with its metadata schema, are quarantined for identical
reasons and must be refused identically. Only the resolver differs, and that difference is
one lookup here.

Quarantine is computed on demand from ``(repo, catalogs)`` and never persisted — the same
discipline as the schema resolution it wraps — so it self-clears the moment the conflicting
profiles or bindings change. Class A (an undefined binding) is a startup concern: it aborts
the engagement repo at boot (WU-Q1) and therefore never reaches a running write boundary, so
here every conflict is Class B (scoped).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from src.application.artifacts.schema import (
    compute_effective_attribute_schema,
    compute_effective_connection_metadata_schema,
)
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.ontology_representation.profile_registry import ProfileConflict
from src.domain.ontology_representation.specializations import ConceptKind

_Resolver = Callable[..., tuple[dict[str, Any] | None, list[str]]]

#: The effective-schema resolver per concept kind. Adding a kind means adding a resolver,
#: not another copy of the quarantine rules.
_RESOLVERS: dict[ConceptKind, _Resolver] = {
    "entity": compute_effective_attribute_schema,
    "connection": compute_effective_connection_metadata_schema,
}


def pair_quarantine_conflicts(
    repo_root: Path,
    concept_kind: ConceptKind,
    subject: str,
    specialization_slugs: Sequence[str],
    *,
    catalogs: RuntimeCatalogs,
) -> tuple[ProfileConflict, ...]:
    """The scoped (Class B) conflicts for one applied-specialization set, or empty when the
    pair resolves cleanly. Every merge conflict is Class B — an incompatible-type
    redefinition — so it is reported directly (a running engagement backend has already
    ruled out Class A at startup)."""
    _schema, merge_conflicts = _RESOLVERS[concept_kind](
        repo_root,
        subject,
        list(specialization_slugs),
        specialization_catalog=catalogs.specializations,
        profile_registry=catalogs.profiles,
    )
    return tuple(ProfileConflict("scoped", message) for message in merge_conflicts)


def compute_quarantine_set(
    repo_root: Path, catalogs: RuntimeCatalogs
) -> dict[tuple[ConceptKind, str, str], tuple[ProfileConflict, ...]]:
    """Every quarantined ``(concept kind, type, specialization)`` triple with its reasons,
    over the whole catalog — entities and connections alike. Confined by construction: each
    pair is resolved independently, so one conflicting pair never taints its siblings."""
    quarantined: dict[tuple[ConceptKind, str, str], tuple[ProfileConflict, ...]] = {}
    subjects: list[tuple[ConceptKind, frozenset[str]]] = [
        ("entity", catalogs.ontology.all_entity_type_names()),
        ("connection", catalogs.ontology.all_connection_type_names()),
    ]
    for concept_kind, type_names in subjects:
        for type_name in type_names:
            _collect_pairs(repo_root, concept_kind, str(type_name), catalogs, quarantined)
    return quarantined


def _collect_pairs(
    repo_root: Path,
    concept_kind: ConceptKind,
    type_name: str,
    catalogs: RuntimeCatalogs,
    into: dict[tuple[ConceptKind, str, str], tuple[ProfileConflict, ...]],
) -> None:
    for specialization in catalogs.specializations.for_type(concept_kind, type_name):
        conflicts = pair_quarantine_conflicts(
            repo_root, concept_kind, type_name, (specialization.slug,), catalogs=catalogs
        )
        if conflicts:
            into[(concept_kind, type_name, specialization.slug)] = conflicts


class ProfileQuarantineError(ValueError):
    """A create/edit was refused because its ``(type, specialization)`` pair is quarantined.
    A ``ValueError`` so every transport surfaces it through the existing write rejection
    path (REST → HTTP 400, MCP → tool error)."""

    def __init__(
        self,
        concept_kind: ConceptKind,
        subject: str,
        specialization: str,
        conflicts: tuple[ProfileConflict, ...],
    ) -> None:
        self.concept_kind = concept_kind
        self.artifact_type = subject
        self.specialization = specialization
        self.conflicts = conflicts
        pair = f"{subject}/{specialization}" if specialization else subject
        noun = "attribute profile" if concept_kind == "entity" else "metadata profile"
        detail = "; ".join(conflict.message for conflict in conflicts)
        super().__init__(
            f"Cannot write {concept_kind} {pair}: its {noun} is quarantined by a conflict — {detail}. "
            "Fix the conflicting named profiles or unbind one, then retry."
        )


def assert_not_quarantined(
    repo_root: Path,
    concept_kind: ConceptKind,
    subject: str,
    specialization_slugs: Sequence[str],
    *,
    catalogs: RuntimeCatalogs,
) -> None:
    """Reject a write whose applied-specialization set resolves to a quarantined schema. The
    single gate every transport passes through (WU-Q3), closing the gap where the write path
    only ever saw the base-type schema."""
    conflicts = pair_quarantine_conflicts(repo_root, concept_kind, subject, specialization_slugs, catalogs=catalogs)
    if conflicts:
        specialization = next((slug for slug in specialization_slugs if slug), "")
        raise ProfileQuarantineError(concept_kind, subject, specialization, conflicts)


