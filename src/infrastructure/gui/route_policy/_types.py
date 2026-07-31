"""Row type and vocabulary for the REST route-policy manifest.

The manifest is the *enforceable* form of the addressing decision: one row per REST
operation this backend serves, carrying the classifications that the router decorator
cannot express and that several independent registries would otherwise each restate —
authorization identity, cache policy, conditional-read eligibility, client/proxy timeout
class, and the response contract.

Why a row type rather than a dict-of-tuples: every field below is a closed vocabulary, and
the invariants that make the fitness functions non-tautological (identity parameters are
*declared* and *appear in the template*; an action segment belongs only to an operation row)
are checkable at construction. A malformed row therefore fails at import, not in the one
test that happens to look at it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

#: What the operation addresses. Load-bearing for the addressing fitness functions:
#: ``detail``/``subresource`` rows must carry identity in the path, ``collection``/``catalog``
#: rows must carry none, and only ``operation`` rows may end in an action segment.
ResourceKind = Literal[
    "collection",  # addresses a set: list reads and creates
    "detail",  # addresses exactly one resource by its identity
    "subresource",  # addresses a named part or relation of one identified resource
    "operation",  # a command; the final segment names an action, not a stored thing
    "singleton",  # one addressable resource of which there is exactly one, so it has no id
    "catalog",  # a vocabulary or aggregate with no repository identity to address
    "stream",  # a long-lived event stream
]

#: Kinds that address no single identified resource, so may declare no identity parameter.
_IDENTITY_FREE_KINDS = frozenset({"collection", "singleton", "catalog", "stream"})

#: Which policy domain a write belongs to. ``repository`` writes are gated by
#: ``REST_MUTATION_MANIFEST`` + ``authorized_write``; ``assurance`` writes are gated by the
#: confidential store's own unlock/capability checks; ``none`` covers reads *and* the
#: write-shaped operations (previews, plans, query execution) that mutate nothing.
MutationDomain = Literal["repository", "assurance", "none"]

#: ``Cache-Control`` this operation's responses carry — success **and** error alike.
#: Independent of ``ConditionalRead``: a confidential response is ``no-store`` precisely
#: because it is ineligible for revalidation, and conflating the two would strip it.
CacheDirective = Literal["no-store", "no-cache", "private", "public"]

#: Whether the operation participates in ETag revalidation. ``etag`` is an allowlist entry
#: claiming the body is a pure function of the indexed model generation and the URL.
ConditionalRead = Literal["none", "etag"]

#: Named timeout class, consumed by the HTTP client and verified against the dev proxy.
#: ``derived-graph`` covers long-running derivation from the model — graph traversal,
#: viewpoint execution and diagram rendering; ``streaming`` never times out.
TimeoutClass = Literal["default", "derived-graph", "streaming"]

#: Response contracts that are deliberately not a JSON DTO.
BODYLESS = "bodyless"
MEDIA = "media"
STREAM = "stream"
_CONTRACT_SENTINELS = frozenset({BODYLESS, MEDIA, STREAM})

MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_METHODS = MUTATION_METHODS | {"GET"}

_PATH_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_DTO_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


class RoutePolicyError(ValueError):
    """A manifest row that cannot be a valid policy statement."""


@dataclass(frozen=True, slots=True)
class RouteRow:
    """One REST operation's canonical address and the policies keyed off it."""

    method: str
    template: str
    resource_kind: ResourceKind
    operation_id: str
    response_contract: str
    identity_parameters: tuple[str, ...] = ()
    mutation_domain: MutationDomain = "none"
    cache_directive: CacheDirective = "no-store"
    conditional_read: ConditionalRead = "none"
    timeout_class: TimeoutClass = "default"

    def __post_init__(self) -> None:
        if self.method not in _METHODS:
            raise RoutePolicyError(f"{self.operation_id}: unsupported method {self.method!r}")
        if not self.template.startswith("/"):
            raise RoutePolicyError(f"{self.operation_id}: template must be absolute")
        declared = set(self.identity_parameters)
        in_template = set(_PATH_PARAM_RE.findall(self.template))
        if declared != in_template:
            raise RoutePolicyError(
                f"{self.operation_id}: identity_parameters {sorted(declared)} do not match the "
                f"path parameters {sorted(in_template)} of {self.template!r}"
            )
        if self.resource_kind in ("detail", "subresource") and not declared:
            raise RoutePolicyError(
                f"{self.operation_id}: a {self.resource_kind} row addresses one resource, so its "
                "identity must be a path parameter"
            )
        if self.resource_kind in _IDENTITY_FREE_KINDS and declared:
            raise RoutePolicyError(
                f"{self.operation_id}: a {self.resource_kind} row addresses no single resource, "
                f"yet declares identity {sorted(declared)}"
            )
        if self.mutation_domain != "none" and self.method not in MUTATION_METHODS:
            raise RoutePolicyError(f"{self.operation_id}: a GET may not declare a mutation domain")
        if (
            self.conditional_read == "etag"
            and self.cache_directive not in ("no-cache", "private", "public")
        ):
            raise RoutePolicyError(
                f"{self.operation_id}: an ETag promises revalidation, which {self.cache_directive!r} "
                "forbids"
            )
        if self.conditional_read == "etag" and self.method != "GET":
            raise RoutePolicyError(f"{self.operation_id}: only a GET may carry an ETag")
        if (
            self.response_contract not in _CONTRACT_SENTINELS
            and not _DTO_NAME_RE.match(self.response_contract)
        ):
            raise RoutePolicyError(
                f"{self.operation_id}: response_contract must be a DTO class name or one of "
                f"{sorted(_CONTRACT_SENTINELS)}, not {self.response_contract!r}"
            )

    @property
    def key(self) -> tuple[str, str]:
        """The ``(METHOD, template)`` pair every path-keyed registry is keyed by."""
        return (self.method, self.template)

    @property
    def is_write_shaped(self) -> bool:
        return self.method in MUTATION_METHODS

    @property
    def literal_segments(self) -> tuple[str, ...]:
        """Path segments that are not identity parameters, below ``/api``."""
        return tuple(
            segment
            for segment in self.template.split("/")
            if segment and not _PATH_PARAM_RE.fullmatch(segment)
        )


def path_parameters(template: str) -> tuple[str, ...]:
    """The path-parameter names of a route template, in order of appearance."""
    return tuple(_PATH_PARAM_RE.findall(template))
