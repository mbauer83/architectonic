/**
 * Every `route.query` use in the GUI, classified.
 *
 * The migration's risk is not the four obvious `?id=` routes — it is the ones nobody remembers.
 * A query key that carries *identity* has to become a path parameter; one that carries a filter,
 * a piece of view state, or an input to an operation belongs exactly where it is. The only way to
 * be sure which is which is to enumerate them, so this table is the enumeration and the
 * accompanying test proves the enumeration is complete in both directions.
 *
 * Keys are `<path under src/>#<query key>`. A use that reads the whole query object — a spread, a
 * destructure, or an access under a computed key — is recorded as `#*` and classified by what the
 * surrounding code does with it.
 *
 * **The table holds no `identity` entry**, which is Phase 2's exit criterion: every resource the
 * GUI addresses, it addresses by path. The role stays in the vocabulary — a new query key that
 * carries identity has to be classifiable as the mistake it is, and the completeness test then
 * fails rather than the key quietly joining the filters.
 */

export type QueryParameterRole =
  /** Names the resource the route addresses. Belongs in the path. */
  | 'identity'
  /** Narrows a collection. Removing it returns the whole collection, so it belongs in the query. */
  | 'filter'
  /** How the page is shown — the view mode, the selected row. Not addressable state. */
  | 'presentation'
  /** An operand of an operation the page performs, not an address. */
  | 'operation-input'

export const QUERY_PARAMETER_ROLES: Readonly<Record<string, QueryParameterRole>> = {
  // ── filter: narrowing a collection ────────────────────────────────────────
  'ui/views/EntitiesView.vue#domain': 'filter',
  'ui/views/EntitiesView.vue#group': 'filter',
  'ui/views/EntitiesView.vue#type': 'filter',
  'ui/views/EntitiesView.vue#viewpoint': 'filter',
  'ui/views/EntitiesView.vue#*': 'filter',
  'ui/views/SearchView.vue#q': 'filter',
  'ui/views/AssuranceBrowseView.vue#analysis': 'filter',
  'ui/views/AssuranceBrowseView.vue#*': 'filter',
  'ui/composables/useDiagramsListState.ts#type': 'filter',
  'ui/composables/useDiagramsListState.ts#group': 'filter',
  'ui/composables/useDiagramsListState.ts#*': 'filter',
  'ui/composables/useDocumentsListState.ts#group': 'filter',
  'ui/composables/useDocumentsListState.ts#*': 'filter',
  'ui/composables/useTierFacet.ts#tier': 'filter',
  'ui/composables/useTierFacet.ts#*': 'filter',
  // The graph filter's exclusions, so a filtered graph is a link. One key holding `level:value`
  // pairs: the level ids belong to whichever meta-ontology is loaded, so they cannot be enumerated
  // here — which is why the key is `hide` rather than one key per level.
  'ui/composables/useGraphFacets.ts#hide': 'filter',
  'ui/composables/useGraphFacets.ts#*': 'filter',
  'ui/components/NavBar.vue#viewpoint': 'filter',
  'ui/components/NavBar.vue#*': 'filter',
  'ui/views/EntityDetailView.vue#*': 'filter',

  // ── presentation state ───────────────────────────────────────────────────
  'ui/views/EntitiesView.vue#view': 'presentation',
  'ui/views/AssuranceBrowseView.vue#view': 'presentation',
  'ui/views/AssuranceBrowseView.vue#node_id': 'presentation',
  // Which of the workspace's tables is open: the analysis is the same whichever tab shows it.
  'ui/views/StressWorkspaceView.vue#tab': 'presentation',
  // The diagram a candidate is drawn and sketched on: the candidate is the same on any diagram.
  'ui/views/CandidateArchitectureView.vue#diagram': 'presentation',
  // Carried whole to a candidate stacked on the one being read, so it opens on the same diagram.
  'ui/views/CandidateArchitectureView.vue#*': 'presentation',
  // The diagram compared candidates are drawn on: the comparison is the same on any diagram.
  'ui/views/CandidateComparisonView.vue#diagram': 'presentation',
  // The diagram reader's reading — `focus`, `reach`, `view` — so a reading is a link. What is being
  // looked at on the one diagram the path addresses, not which diagram: the page is the same without it.
  'ui/composables/useReadingAddress.ts#*': 'presentation',

  // ── operation input ──────────────────────────────────────────────────────
  'ui/views/PromoteView.vue#*': 'operation-input',
  'ui/views/CreateDiagramView.vue#type': 'operation-input',
  // The collection the reader was browsing, seeding a new artifact's home. An operand of the
  // create rather than a filter: it narrows nothing, and rather than addressing the page it
  // supplies its first answer, which the reader can then change. Read by the home control itself,
  // so no create form can be the one that forgets to.
  'ui/components/ArtifactHomeSelect.vue#group': 'operation-input',
  'ui/views/ViewpointsManagementView.vue#seedEntityCriteria': 'operation-input',
  'ui/views/EphemeralViewpointQueryView.vue#slug': 'operation-input',
  // A comparison of candidate architectures addresses no stored thing: which candidates (`candidate`,
  // repeated) and the base they are read against are its operands, so a comparison is a link.
  'ui/views/CandidateComparisonView.vue#candidate': 'operation-input',
  'ui/views/CandidateComparisonView.vue#base': 'operation-input',
  // Adding or dropping a candidate, or choosing the base or the diagram, rewrites the query it keeps.
  'ui/views/CandidateComparisonView.vue#*': 'operation-input',
  // The graph explorer's viewpoint half owns the address for `viewpoint`, `param.*` and the
  // verification pins, so the uses sit with that composable rather than with the view.
  'ui/composables/useGraphViewpointExploration.ts#viewpoint': 'operation-input',
  'ui/composables/useGraphViewpointExploration.ts#*': 'operation-input',
  'ui/components/ExecutionLinkActions.vue#*': 'operation-input',
  'ui/components/ExecutionReferenceBar.vue#*': 'operation-input',
  'ui/components/ViewpointTablePage.vue#*': 'operation-input',
}

/** Uses that still read identity out of the query. Empty, and a regression if it is not. */
export const identityQueryUses = (): string[] =>
  Object.entries(QUERY_PARAMETER_ROLES)
    .filter(([, role]) => role === 'identity')
    .map(([use]) => use)
    .sort()
