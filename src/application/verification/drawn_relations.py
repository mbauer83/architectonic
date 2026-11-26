"""What a diagram body draws, bound to the model the way verification binds it: one reading, two askers.

The verifier's completeness rules (E314–E317) ask, of each relation a body draws, which element each end is
and which model connections fit it; the upgrade step that lists drawn relations in `connection-ids-used`
(d14) asks the same question to make those rules stop refusing a diagram written before they applied. It
asked it its own way — aliases from the diagram's statements only, connections from the model files — so a
relation whose alias only an entity's display alias or the registry resolves was skipped by the step and
still refused after the upgrade. Both now read it here.

`diagram_body_is_reconcile_owned` is here for the same reason: it decides which diagrams the rules apply to,
and the write path's refresh and the step ask it too.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from src.application.puml_relation_parsing import DeclaredRelation, declared_relations
from src.application.verification._verifier_rules_puml_relations import _build_alias_lookup, _normalize_puml_alias
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import stable_conn_id, stable_id
from src.domain.diagrams.diagram_type_field import diagram_type_of
from src.domain.modules.catalogs import DiagramTypeCatalog
from src.domain.ontology_representation.ontology_protocol import StoreGraphProjectingDiagramType


def diagram_body_is_reconcile_owned(fm: Mapping[str, object], diagram_type_catalog: DiagramTypeCatalog) -> bool:
    """True when the ArchiMate reconcile is what refreshes this diagram's body.

    The single decision the refresh dispatch matrix makes, asked from frontmatter alone: a type whose
    body is rendered from ``diagram-entities`` (``body_is_rendered_from_diagram_entities``, the rule's
    owner — the write path asks it too), a type drawn from the assurance store
    (``StoreGraphProjectingDiagramType``) or a projector-owned diagram (``scoped-by`` binding) is
    re-rendered from stored state. Everything else is reconciled from its bindings — and only there are
    body-expressed-but-unbound relations at risk of deletion.

    An ArchiMate diagram's ``diagram-entities`` holds statements about its instances (labels,
    occurrences, icons), not its body's source; reading "non-empty" as "standalone" switched these
    checks off for every ArchiMate diagram carrying one statement (B112, the verifier's half of B96).

    The write path's refresh asks this same question to decide whether to reconcile, so the two cannot
    disagree about which diagrams the model reconcile owns.
    """
    module = diagram_type_catalog.find_diagram_type(diagram_type_of(fm))
    if module is None:
        # A type no module in this deployment describes — the assurance family without the confidential
        # store, say — is neither reconciled nor checked as ArchiMate: its stored state is all there is.
        return False
    if module.body_is_rendered_from_diagram_entities or isinstance(module, StoreGraphProjectingDiagramType):
        return False
    bindings = fm.get("bindings")
    return not any(
        isinstance(b, dict)
        and b.get("correspondence_kind") == "scoped-by"
        and isinstance(b.get("subject"), dict)
        and b["subject"].get("kind") == "diagram"
        and isinstance(b.get("target"), dict)
        and b["target"].get("entity_id")
        for b in (bindings if isinstance(bindings, list) else [])
    )


def is_nesting(relation: DeclaredRelation) -> bool:
    """Whether *relation* is drawn by nesting one element inside another rather than by an arrow."""
    return relation.connection_type is None and relation.arrow == ""


@dataclass(frozen=True)
class DrawnRelation:
    """One relation a body draws, as the model reads it."""

    relation: DeclaredRelation
    #: The element each end stands for; None where the alias resolves to none.
    source_id: str | None
    target_id: str | None
    #: The model connections that fit: those joining the two ends, of the type an arrow states.
    fitting: tuple[str, ...]
    #: Whether `connection-ids-used` lists one of them.
    listed: bool

    @property
    def nesting(self) -> bool:
        return is_nesting(self.relation)


def alias_resolver(
    content: str, fm: Mapping[str, object], registry: ArtifactRegistry, stereotype_map: Mapping[str, str],
) -> Callable[[str], str | None]:
    """The element an alias of this body stands for: as the body, the frontmatter or the registry declares it."""
    lookup = _build_alias_lookup(content, dict(fm), registry, stereotype_map)
    return lambda alias: lookup.get(alias) or lookup.get(_normalize_puml_alias(alias))


def connections_between(registry: ArtifactRegistry, src_id: str, tgt_id: str) -> list:
    """Model connections joining the pair, in either direction."""
    src_short, tgt_short = stable_id(src_id), stable_id(tgt_id)
    return [
        record
        for record in registry.find_connections_for(src_id, direction="any")
        if {stable_id(record.source), stable_id(record.target)} == {src_short, tgt_short}
    ]


def listed_connection_stable_ids(fm: Mapping[str, object]) -> set[str]:
    """The stable form of every id in connection-ids-used — the same normalisation the
    E302 rule compares with, so listed-vs-model can never disagree on id syntax."""
    raw = fm.get("connection-ids-used")
    return {stable_conn_id(str(cid)) for cid in raw} if isinstance(raw, list) else set()


def drawn_relations(
    content: str, fm: Mapping[str, object], registry: ArtifactRegistry, stereotype_map: Mapping[str, str],
    *, resolve: Callable[[str], str | None] | None = None,
) -> tuple[DrawnRelation, ...]:
    """Each distinct relation the body draws, its ends resolved and the model connections that fit it."""
    resolved = resolve or alias_resolver(content, fm, registry, stereotype_map)
    listed = listed_connection_stable_ids(fm)
    seen: set[tuple[str, str, str | None, bool]] = set()
    found: list[DrawnRelation] = []
    for relation in declared_relations(content, stereotype_map):
        key = (relation.source_alias, relation.target_alias, relation.connection_type, is_nesting(relation))
        if key in seen:
            continue
        seen.add(key)
        src_id, tgt_id = resolved(relation.source_alias), resolved(relation.target_alias)
        candidates = connections_between(registry, src_id, tgt_id) if src_id is not None and tgt_id is not None else []
        fitting = tuple(
            sorted(c.artifact_id for c in candidates if relation.connection_type in (None, c.conn_type))
        )
        found.append(DrawnRelation(
            relation, src_id, tgt_id, fitting, any(stable_conn_id(c) in listed for c in fitting),
        ))
    return tuple(found)
