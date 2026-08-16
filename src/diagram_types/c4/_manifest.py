"""The C4 module manifest: the strategy the refresh/diff path reaches the projection through.

Its own module because it is registration rather than algorithm — the composition root imports
`MANIFEST` from here, and `_type.py` imports this module for the side effect of declaring it.
"""

from __future__ import annotations

from src.diagram_types.c4._projection import project_c4_scope
from src.domain.modules.module_manifest import DiagramTypeModuleManifest
from src.domain.relationships.derivation_types import CandidateSet, ModelQuery, StrategySpec
from src.domain.viewpoints.view_derivations import SourceModelSnapshot


def _derive(
    params: dict[str, object],
    snapshot: SourceModelSnapshot,
    query: ModelQuery,
) -> CandidateSet:
    roots = snapshot.root_entity_ids or ()
    if not roots:
        single = snapshot.root_entity_id or str(params.get("scope_entity_id", ""))
        roots = (single,) if single else ()
    if not roots:
        return CandidateSet()
    raw_person_types = params.get("person_archimate_types")
    person_types: frozenset[str] = (
        frozenset(str(t) for t in raw_person_types)
        if isinstance(raw_person_types, (list, tuple, set, frozenset))
        else frozenset()
    )
    return project_c4_scope(
        str(params.get("diagram_type", "")),
        roots,
        query,
        internal_c4_type=str(params.get("internal_c4_type", "container")),
        scope_entity_type=str(params.get("scope_entity_type", "")),
        person_archimate_types=person_types,
    ).to_candidate_set()


MANIFEST = DiagramTypeModuleManifest(
    id="c4",
    version=1,
    compatible_ontologies=("archimate-4-0", "sysml_v2_min"),
    ontology_role_mapping={},  # K2-followon: parameterise projection per active ontology
    strategies=((
        StrategySpec(name="c4.scope-projection", version=1, supported_filters=frozenset({"repo_scope"})),
        _derive,
    ),),
)
