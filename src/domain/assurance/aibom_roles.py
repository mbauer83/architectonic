"""AIBOM derivation-role vocabulary and bindings.

The exporter fills a **closed** set of named derivation roles — it must know what each means
to place it in the ML-BOM. HOW a repository expresses each role is **open**: a role binds to
the connection type(s) and target specialization(s) that realise it, and a repo may override
the binding for its own conventions. The roles are closed; the bindings are open.

This module is pure domain: the vocabulary, the typed binding record, a parser that rejects
an unknown role name (never silently ignores it), and a per-role override merge. Loading the
shipped defaults and the repo override, and consuming the bindings during derivation, live in
the application/infrastructure layers (Streams A-loader and B).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: The closed derivation-role vocabulary. Adding a role is an ontology + exporter change, not
#: a repo-config one — an override naming anything outside this set is an error.
AIBOM_DERIVATION_ROLES: frozenset[str] = frozenset(
    {
        "trained-on",
        "evaluated-on",
        "fine-tuned-from",
        "embeds-into",
        "served-by",
        "uses-tool",
        "guarded-by",
        "governed-by",
        "consumes-prompt",
    }
)


class DerivationRoleError(ValueError):
    """A role-binding declaration is malformed or names a role outside the closed vocabulary.
    A ``ValueError`` so loaders surface it through the ordinary config-error path."""


@dataclass(frozen=True)
class RoleBinding:
    """How one derivation role is realised: connections of these type(s) to targets carrying
    (any of) these specialization(s). An empty ``target_specializations`` means the role is
    matched by connection type alone."""

    role: str
    connection_types: tuple[str, ...]
    target_specializations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DerivationRoleBindings:
    """The resolved role→binding map (shipped defaults with any repo overrides applied)."""

    bindings: Mapping[str, RoleBinding]

    @staticmethod
    def empty() -> DerivationRoleBindings:
        return DerivationRoleBindings(bindings={})

    def get(self, role: str) -> RoleBinding | None:
        return self.bindings.get(role)

    def bound_roles(self) -> frozenset[str]:
        return frozenset(self.bindings)

    def unbound_roles(self) -> frozenset[str]:
        """Vocabulary roles with no binding — a coverage concern, not an error: an unbound
        role yields a coverage finding, never a silently empty BOM (PLAN §5)."""
        return AIBOM_DERIVATION_ROLES - self.bound_roles()


def role_bindings_from_mapping(raw: object, *, label: str) -> DerivationRoleBindings:
    """Parse a ``{roles: {role: {connection_types: [...], target_specializations: [...]}}}``
    mapping into typed bindings. An unrecognised role name, or a malformed entry, is a
    ``DerivationRoleError`` — never silently dropped."""
    if not isinstance(raw, Mapping):
        raise DerivationRoleError(f"{label}: top-level YAML value must be a mapping")
    roles_raw = raw.get("roles", {})
    if not isinstance(roles_raw, Mapping):
        raise DerivationRoleError(f"{label}: 'roles' must be a mapping")
    bindings: dict[str, RoleBinding] = {}
    for role, entry in roles_raw.items():
        role_name = str(role)
        if role_name not in AIBOM_DERIVATION_ROLES:
            raise DerivationRoleError(
                f"{label}: unknown derivation role {role_name!r} "
                f"(closed vocabulary: {', '.join(sorted(AIBOM_DERIVATION_ROLES))})"
            )
        if not isinstance(entry, Mapping):
            raise DerivationRoleError(f"{label}: binding for {role_name!r} must be a mapping")
        conn_types = _str_tuple(entry.get("connection_types"))
        if not conn_types:
            raise DerivationRoleError(f"{label}: role {role_name!r} must bind at least one connection_type")
        bindings[role_name] = RoleBinding(
            role=role_name,
            connection_types=conn_types,
            target_specializations=_str_tuple(entry.get("target_specializations")),
        )
    return DerivationRoleBindings(bindings=bindings)


def merge_role_bindings(
    base: DerivationRoleBindings, override: DerivationRoleBindings
) -> DerivationRoleBindings:
    """Shipped defaults with per-role repo overrides applied: an override replaces exactly the
    role it names and leaves every other default untouched."""
    merged = dict(base.bindings)
    merged.update(override.bindings)
    return DerivationRoleBindings(bindings=merged)


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if str(v))
    return ()
