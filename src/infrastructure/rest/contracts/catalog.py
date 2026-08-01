"""Response contracts for the repository's own catalog reads: counts, identity, modules, taxonomy.

What a client asks before it asks about any particular artifact — how big the repository is, which
backend is serving it, which modules are loaded, and how the entity types are grouped. None of them
name an artifact, which is why they sit together rather than beside the entity contracts.

The maps here are keyed by *authored* vocabulary — domain names, group names, connection types — so they
stay open maps with closed values. Enumerating their keys would move the ontology's vocabulary into a
second place, and a term added to a module and not mirrored here would then fail its own response.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepositoryStatsResponse(_Closed):
    """How much of each kind the served repository holds, and how it distributes.

    The four totals are the artifact kinds the index stores. The breakdowns are one map per axis rather
    than a nested tree, because each is a different question — "which domains is the model in" is not
    the same shape of answer as "how is it laid out across groups" — and a client renders one at a time.
    """

    entities: int
    connections: int
    diagrams: int
    documents: int
    #: Keyed by domain name; entities carrying no domain count under the empty string.
    entities_by_domain: dict[str, int]
    connections_by_type: dict[str, int]
    documents_by_type: dict[str, int]
    entities_by_group: dict[str, int]
    diagrams_by_group: dict[str, int]
    documents_by_group: dict[str, int]


class BackendIdentityResponse(_Closed):
    """Which repository this backend serves, and which build is serving it.

    Exists because ``arch-repair upgrade --commit`` refuses to run against a repository a live backend
    holds open, and needs the roots to decide that — ``/api/stats`` carries counts but no paths. The
    roots are realpath-normalised, so the comparison is not defeated by a symlinked working copy.
    """

    repo_roots: list[str]
    #: The installed distribution's version, or ``"unknown"`` when running from a tree that was never
    #: installed. Reported rather than omitted: "which build" with no answer is still the answer.
    software_version: str


class LoadedModuleResponse(_Closed):
    """One registered module — enabled, its requirements satisfied — and how much it contributes."""

    name: str
    #: Which class of model the module describes; what decides whether its content is confidential.
    module_class: str
    enabled: bool
    #: Other modules it needs before it can load.
    requires: list[str]
    entity_type_count: int
    connection_type_count: int


class LoadedModuleListResponse(_Closed):
    """The loaded modules, in name order.

    An envelope rather than a bare array, which is what this route used to serve. Every other collection
    read on this surface answers with one, and a top-level array is the one shape that cannot later carry
    a count, a cursor or a "some were skipped" note without breaking every client — so the outlier is
    the array, not the envelope.
    """

    modules: list[LoadedModuleResponse]


class TaxonomyTypeResponse(_Closed):
    """One entity type within a domain, with how many entities the repository has of it."""

    name: str
    count: int


class TaxonomyDomainResponse(_Closed):
    """One domain and the types found in it.

    ``count`` is the domain total, which is the sum over ``types`` — sent rather than left to the client
    so a collapsed domain can show its size without the caller re-adding the rows.
    """

    name: str
    count: int
    types: list[TaxonomyTypeResponse]


class EntityTaxonomyResponse(_Closed):
    """The entity types the repository actually contains, grouped by domain.

    Only domains with content appear, in the module registry's declared order with any unregistered
    domain after them — a tree of every *possible* type would bury the handful the model uses. So this
    describes the repository, not the ontology; ``/api/authoring-guidance`` is the read for the latter.
    """

    domains: list[TaxonomyDomainResponse]
