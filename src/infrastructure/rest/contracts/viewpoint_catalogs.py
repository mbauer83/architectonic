"""The authoring-time vocabulary the criteria editor offers, and the query summary it previews.

Two catalogues in one place because they answer the same question at the same moment: what may this
definition say, and what does what it says mean in words. Neither appears in a result.

The registries snapshot served here is the one save-mode validation itself resolves against, so a
picker cannot offer a value the save would then refuse.
"""

from __future__ import annotations

from src.infrastructure.rest.contracts.wire_shape import Closed


class BindingCatalogResponse(Closed):
    """What a binding may select, aggregate and declare as its result type.

    ``result_types`` are type *expressions* rather than an enumeration — ``entity[type-slug]`` and
    ``tuple[result-type, ...]`` are grammar with holes in them, which is why they are strings and
    not a closed vocabulary the way the other two lists are.
    """

    select: list[str]
    aggregate: list[str]
    result_types: list[str]


class ParameterCatalogResponse(Closed):
    """The element kinds a declared parameter may take. Cardinality is orthogonal and is not a
    type name, so it is not in this list."""

    types: list[str]


class DerivedCatalogResponse(Closed):
    """The three axes a derived attribute is configured on: how far to walk, what evidence counts,
    and how to collapse the result."""

    traversal: list[str]
    certainty: list[str]
    reduce: list[str]


class ConnectionDerivationEntryResponse(Closed):
    """A connection type's part in relationship derivation.

    ``strength`` is null for a role that does not rank — a specialization or a dynamic relation is
    not weaker or stronger evidence than another of its kind, it is a different kind of evidence.
    """

    role: str
    strength: int | None


class CriteriaCatalogResponse(Closed):
    """Everything the criteria-tree builder's pickers are fed from, in one request.

    One snapshot rather than a request per picker: the panels are filled together, and two of them
    resolved against different snapshots could offer a pair that never validates.

    The two ``*_attribute_enums`` maps are the value picker's switch from free text to a dropdown.
    A path absent from them is open, not empty — validation ignores them entirely, so a value
    outside a declared set is never retroactively rejected.
    """

    entity_types: list[str]
    connection_types: list[str]
    specialization_slugs: list[str]
    #: Attribute path → the kind it holds (``string``, ``integer``, ``array``, …), in the same flat
    #: namespace the criteria tree addresses.
    entity_attribute_types: dict[str, str]
    connection_attribute_types: dict[str, str]
    entity_attribute_enums: dict[str, list[str]]
    connection_attribute_enums: dict[str, list[str]]
    symmetric_connection_types: list[str]
    reserved_entity_paths: list[str]
    reserved_connection_paths: list[str]
    #: How deep a nested endpoint-criteria chain may go before save-time validation refuses it.
    depth_cap: int
    #: Entity type → its owning domain, so a scope picker can group by domain and offer
    #: "exclude this whole domain" without a second lookup per type.
    entity_type_domains: dict[str, str]
    bindings: BindingCatalogResponse
    parameters: ParameterCatalogResponse
    derived: DerivedCatalogResponse
    connection_derivation: dict[str, ConnectionDerivationEntryResponse]


class ViewpointQuerySummaryResponse(Closed):
    """A plain-language rendering of an in-progress query.

    The same renderer the MCP list and execute tools use, so the builder's live preview cannot
    disagree with what those surfaces say about the same definition later.
    """

    summary: str
