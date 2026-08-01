"""The write-help catalogue: every type an author may create, and the vocabulary to create it in.

Closed per level, which is the rule decision 6 settles. The envelope, the conventions, the artifact
types, the stereotypes and the closing prose are determinate and closed here. The two big catalogues
are open *maps* keyed by an ontology term — 58 entity types and 62 connection types, and the key set is
the ontology's to decide — with a **closed value**: a type's declaration carries a fixed set of facts,
and enumerating the keys would freeze today's ontology into a delivery contract.

``viewpoints`` is the exception, and deliberately so. It is a documentation block about the viewpoint
query language, keyed by topic and heterogeneous by nature — a schema version, a comparator glossary, a
list of reserved paths, a worked example. Declaring a field per topic would make this DTO the place
every change to the query language has to be mirrored, and the mirror is what would go stale.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityTypeCatalogEntry(_Closed):
    """What one entity type is: its id prefix, where it sits, and what it counts as.

    ``hierarchy`` is the path from domain to type, so a picker can group without a second lookup;
    ``classes`` are the sets it belongs to, which is what a permitted-relationship rule matches on.
    """

    prefix: str
    hierarchy: list[str]
    classes: list[str]


class ConnectionTypeCatalogEntry(_Closed):
    """What one connection type is, in the modelling language that defines it.

    ``symmetric`` is load-bearing rather than descriptive: a symmetric relation belongs to neither
    direction, so every count and every arrow depends on it.

    ``language`` is not always ``archimate``: diagram-type modules contribute their own relation
    vocabularies, which is why the ArchiMate mapping is nullable rather than assumed.
    """

    language: str
    # Null for a relation no ArchiMate relationship corresponds to — the ER, sequence and activity
    # languages a diagram-type module contributes have their own vocabularies, and mapping one of
    # theirs onto an ArchiMate relation would assert an equivalence the ontology does not claim.
    archimate_relationship_type: str | None
    symmetric: bool
    puml_arrow: str


class DiagramTypeHelpEntry(_Closed):
    """One diagram type an author may create, and the domains it accepts.

    ``accepted_domains`` empty means it accepts any — an unfiltered picker, not a broken one.
    """

    name: str
    label: str
    accepted_domains: list[str]


class WriteHelpConventions(_Closed):
    """The house rules an author has to follow, stated rather than left to be inferred.

    Five determinate keys with heterogeneous values, so it is a model and not a map: ``statuses`` is
    the lifecycle vocabulary, ``connection_inference`` is a mode-to-meaning glossary, and the other
    three are format rules. Typed as ``dict[str, str]`` this failed validation on two of the five —
    which is what a wrong container type looks like when the payload finally has a contract.
    """

    entity_id_format: str
    puml_alias_format: str
    statuses: list[str]
    dry_run: str
    #: Mode → what inferring connections from PUML stereotypes does in it. A glossary rather than a
    #: list, because choosing a mode means choosing what an unknown stereotype costs: nothing, a
    #: warning, or an error.
    connection_inference: dict[str, str]


class WriteHelpResponse(_Closed):
    """Everything an authoring surface needs to offer a valid write.

    ``entity_types_by_domain`` and ``connection_types_by_language`` are the two catalogues indexed the
    way a picker groups them; the catalogues themselves carry the facts. Both indexes and both
    catalogues are served together because an author choosing a type needs the grouping and the
    declaration in the same breath, and a request per type would be a request per option.

    ``next_steps`` is prose telling the caller which tool to reach for next. It is in the payload
    rather than the docs because the caller is as often an agent as a person, and an agent does not
    read the docs.
    """

    artifact_types: list[str]
    entity_types_by_domain: dict[str, list[str]]
    entity_type_catalog: dict[str, EntityTypeCatalogEntry]
    connection_types_by_language: dict[str, list[str]]
    connection_type_catalog: dict[str, ConnectionTypeCatalogEntry]
    diagram_types: list[DiagramTypeHelpEntry]
    archimate_stereotypes: list[str]
    viewpoints: dict[str, Any]
    conventions: WriteHelpConventions
    next_steps: str
