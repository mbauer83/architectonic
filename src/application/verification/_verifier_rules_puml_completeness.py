"""Rule: every relation a diagram body expresses must be bound, or verification says so.

The reconcile path treats a diagram's bindings (``entity-ids-used`` / ``connection-ids-used``)
as authoritative and deletes what is not listed. A relation the body *draws* but does not *bind*
is therefore data loss waiting for the next refresh — six real ``archimate-influence`` relations
were lost from one motivation view exactly that way while ``artifact_verify`` reported the
repository clean. This rule closes that gap at error severity: verification must fail while the
divergence is still visible, not after the refresh has erased it.

Scope mirrors the refresh dispatch matrix (see ``diagram_sync``): the invariant protects exactly
the diagrams the ArchiMate reconcile owns. Diagram types that own their entities
(``diagram_only_types`` — sequence, C4, datatype, …) speak their own body vocabulary; standalone
diagrams (non-empty ``diagram-entities``) and projector-owned diagrams (``scoped-by`` binding)
are re-rendered from stored state, never reconciled from the body. None of them is checked here.

What is checked, per relation the shared parser reads out of the body:

* An **arrow endpoint that resolves to no entity at all** is an error (E314) — previously a
  silent skip in ``infer_connections_from_puml``, so the drawn relation simply vanished from
  every reader's view.
* An endpoint that resolves to an entity **not listed** in ``entity-ids-used`` is an error
  (E315) — a diagram that hosts entities in a non-empty ``diagram-entities`` is standalone and
  outside this rule's scope altogether, so entity-ids-used is the whole binding surface here.
* A relation whose pair **has** a model connection that is **not listed** in
  ``connection-ids-used`` is an error (E316) — the reconcile would resolve and re-add it, but
  until then the stored bindings disown what the picture asserts.
* An **arrow** whose pair has **no** model connection at all is an error (E317) — nothing backs
  it, so a regeneration can only drop it.
* A relation ``connection-ids-used`` **lists** that the body does not draw is a warning (W307) —
  the same disagreement read the other way. E309 has refused the entity-side equivalent for some
  time; the connection side had no rule, so a wrong claim about which views show a connection went
  unreported. A warning rather than an error because the rule is stated over live model content and
  a repository that verified clean must not fail over frontmatter nobody has touched.

Where the wrong claim persists rather than heals is what makes W307 worth reporting: a
regenerating refresh redraws the missing edge, so the claim becomes true again, while a
``manual-layout`` diagram keeps its body verbatim and unions the references, and a hand-edited file
never heals at all.

Containment nesting is exempt from E317 (not from E316): the generator nests flow-through
events and junction components inside a container purely visually, with no model relation —
see ``build_visual_nesting``. Unbacked nesting is therefore legitimate generated output, and a
re-render reproduces it from the same layout logic, so nothing is lost. Nesting whose pair *is*
model-backed remains subject to E316 — that is the containment blind spot that flattened
``conformance-review``. Likewise a nesting parent that resolves to no entity is skipped rather
than reported: authored grouping rectangles may carry an alias, and they name a box, not an
element.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Literal

from src.application.artifacts.parsing import extract_declared_puml_aliases
from src.application.puml_relation_parsing import (
    declared_relations,
    indirect_nesting_relations,
)
from src.application.verification._verifier_rules_puml_relations import check_diagram_relation_references
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.verification.drawn_relations import (
    alias_resolver,
    connections_between,
    diagram_body_is_reconcile_owned,
    drawn_relations,
)
from src.domain.artifact_id import stable_conn_id, stable_id
from src.domain.diagrams.recorded_references import body_contradicts_reference
from src.domain.modules.catalogs import DiagramTypeCatalog

if TYPE_CHECKING:
    from src.application.runtime_catalogs import RuntimeCatalogs


def check_puml_relation_rules(
    content: str,
    fm: dict,
    registry: ArtifactRegistry,
    file_scope: Literal["enterprise", "engagement", "unknown"],
    result: VerificationResult,
    loc: str,
    *,
    runtime_catalogs: RuntimeCatalogs,
) -> None:
    """Both PUML-relation rules behind one entry point: reference validity, then completeness."""
    stereotype_map = runtime_catalogs.ontology.archimate_stereotype_to_connection_type()
    check_diagram_relation_references(
        content, fm, registry, file_scope, result, loc, stereotype_map=stereotype_map
    )
    check_diagram_relation_completeness(
        content, fm, registry, result, loc,
        stereotype_map=stereotype_map, diagram_type_catalog=runtime_catalogs.diagram_types,
    )


def _drawn_connection_ids(
    content: str,
    registry: ArtifactRegistry,
    resolve: Callable[[str], str | None],
    stereotype_map: Mapping[str, str],
) -> set[str]:
    """The stable id of every model connection the body can be read to draw.

    Indirect nesting counts, which is why it is read here and not only in E316's walk: a body nesting
    C two levels inside A draws ``A --composition--> C`` without stating the pair at any single level,
    and reading one level would report that correct entry as a wrong claim.

    An **untyped** arrow between a pair joined by more than one connection contributes *all* of them.
    It names none of them, so treating any as undrawn would read the reader's own silence as evidence
    against the frontmatter. A typed arrow filters to its type and is therefore decisive — that is
    what lets the rule report anything at all.
    """
    drawn: set[str] = set()
    for relation in (
        *declared_relations(content, stereotype_map),
        *indirect_nesting_relations(content),
    ):
        src_id, tgt_id = resolve(relation.source_alias), resolve(relation.target_alias)
        if src_id is None or tgt_id is None:
            continue
        candidates = connections_between(registry, src_id, tgt_id)
        if relation.connection_type is not None:
            candidates = [c for c in candidates if c.conn_type == relation.connection_type]
        drawn |= {stable_conn_id(c.artifact_id) for c in candidates}
    return drawn


def _check_recorded_connections_are_drawn(
    content: str,
    fm: dict,
    registry: ArtifactRegistry,
    result: VerificationResult,
    loc: str,
    *,
    resolve: Callable[[str], str | None],
    stereotype_map: Mapping[str, str],
) -> None:
    """W307: `connection-ids-used` names a relation the body does not draw.

    The judgement itself is `body_contradicts_reference`, in the domain, because the write path asks
    the same question when it decides what survives a body replacement. Two spellings of it could
    disagree about the same picture, and then a reconcile would drop a reference this rule had just
    said was fine.
    """
    raw = fm.get("connection-ids-used")
    if not isinstance(raw, list) or not raw:
        return
    declared_entities = {
        stable_id(entity_id)
        for alias in extract_declared_puml_aliases(content)
        if (entity_id := resolve(alias)) is not None
    }
    drawn = _drawn_connection_ids(content, registry, resolve, stereotype_map)
    # The diagram's own entity list, as the second ground for a contradiction: an endpoint in
    # neither the body nor here is one no arrow in this body can reach. Supplied only where the
    # frontmatter states it — an absent list is no evidence, not an empty one.
    raw_entities = fm.get("entity-ids-used")
    recorded_entities = (
        {str(entity) for entity in raw_entities} if isinstance(raw_entities, list) else None
    )
    reported: set[str] = set()
    for reference in raw:
        text = str(reference)
        if stable_conn_id(text) in reported:
            continue
        if not body_contradicts_reference(
            text, declared_entities=declared_entities, drawn_stable=drawn,
            recorded_entities=recorded_entities,
        ):
            continue
        reported.add(stable_conn_id(text))
        result.issues.append(Issue(
            Severity.WARNING, "W307",
            f"connection-ids-used lists '{text}' but this view does not draw it — either the body "
            "declares both endpoints and draws no relation between them, or an endpoint is in "
            "neither the body nor entity-ids-used, so nothing here could reach it. The claim that "
            "this view shows the connection is wrong, and impact analysis reads it. Correct it by "
            "passing connection_ids to artifact_edit_diagram — alongside puml, or alongside "
            "puml='auto-sync' on a hand-laid diagram, which keeps the body as it is",
            loc,
        ))


def check_diagram_relation_completeness(
    content: str,
    fm: dict,
    registry: ArtifactRegistry,
    result: VerificationResult,
    loc: str,
    *,
    stereotype_map: Mapping[str, str],
    diagram_type_catalog: DiagramTypeCatalog,
) -> None:
    """Every relation the body expresses is bound; every entity it touches is listed; and every
    relation it claims to draw, it draws."""
    if not diagram_body_is_reconcile_owned(fm, diagram_type_catalog):
        return

    resolve = alias_resolver(content, fm, registry, stereotype_map)
    raw_used = fm.get("entity-ids-used")
    # entity-ids-used is the whole binding surface here: a type whose body renders from
    # ``diagram-entities`` is outside this rule's scope (``diagram_body_is_reconcile_owned``).
    bound_short = {stable_id(str(eid)) for eid in raw_used if eid is not None} if isinstance(raw_used, list) else set()
    reported_unbound_aliases: set[str] = set()

    for drawn in drawn_relations(content, fm, registry, stereotype_map, resolve=resolve):
        relation = drawn.relation
        if drawn.source_id is None or drawn.target_id is None:
            # A nesting endpoint that resolves to nothing is an aliased grouping rectangle —
            # a box, not an element. A *typed* arrow's unknown alias is already E311. Only the
            # bare arrow's unknown alias was nobody's finding until now.
            if not drawn.nesting and relation.connection_type is None:
                unknown = relation.source_alias if drawn.source_id is None else relation.target_alias
                result.issues.append(Issue(
                    Severity.ERROR, "E314",
                    f"diagram body draws a relation '{relation.source_alias} {relation.arrow} "
                    f"{relation.target_alias}' but alias '{unknown}' resolves to no entity",
                    loc,
                ))
            continue

        for alias, entity_id in ((relation.source_alias, drawn.source_id), (relation.target_alias, drawn.target_id)):
            if stable_id(entity_id) not in bound_short and alias not in reported_unbound_aliases:
                reported_unbound_aliases.add(alias)
                result.issues.append(Issue(
                    Severity.ERROR, "E315",
                    f"diagram body draws entity alias '{alias}' ('{entity_id}') which is listed "
                    "neither in entity-ids-used nor in diagram-entities",
                    loc,
                ))

        if drawn.listed:
            continue

        drawn_as = "nesting" if drawn.nesting else relation.arrow or relation.connection_type or "arrow"
        if drawn.fitting:
            result.issues.append(Issue(
                Severity.ERROR, "E316",
                f"diagram body expresses a relation '{relation.source_alias} -> "
                f"{relation.target_alias}' ({drawn_as}) that is not listed in "
                f"connection-ids-used (model candidates: {list(drawn.fitting)}) — the reconcile "
                "treats bindings as authoritative and would not preserve it",
                loc,
            ))
        elif not drawn.nesting:
            # Unbacked *nesting* is legitimate generated output (flow-through events and
            # junctions are nested visually); an unbacked *arrow* can only be dropped by
            # the next regeneration.
            result.issues.append(Issue(
                Severity.ERROR, "E317",
                f"diagram body draws '{relation.source_alias} {relation.arrow} "
                f"{relation.target_alias}' but no model connection exists between the pair — "
                "the drawn relation is not model-backed",
                loc,
            ))

    _check_recorded_connections_are_drawn(
        content, fm, registry, result, loc, resolve=resolve, stereotype_map=stereotype_map,
    )
