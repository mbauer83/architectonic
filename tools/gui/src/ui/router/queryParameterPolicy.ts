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
  'ui/components/NavBar.vue#viewpoint': 'filter',
  'ui/components/NavBar.vue#*': 'filter',
  'ui/views/EntityDetailView.vue#*': 'filter',

  // ── presentation state ───────────────────────────────────────────────────
  'ui/views/EntitiesView.vue#view': 'presentation',
  'ui/views/AssuranceBrowseView.vue#view': 'presentation',
  'ui/views/AssuranceBrowseView.vue#node_id': 'presentation',

  // ── operation input ──────────────────────────────────────────────────────
  'ui/views/PromoteView.vue#*': 'operation-input',
  'ui/views/CreateDiagramView.vue#type': 'operation-input',
  'ui/views/ViewpointsManagementView.vue#seedEntityCriteria': 'operation-input',
  'ui/views/EphemeralViewpointQueryView.vue#slug': 'operation-input',
  'ui/views/GraphExploreView.vue#viewpoint': 'operation-input',
  'ui/views/GraphExploreView.vue#*': 'operation-input',
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
