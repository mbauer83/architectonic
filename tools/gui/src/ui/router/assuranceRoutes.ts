/**
 * The assurance area's routes, as data.
 *
 * Split out of the router module so they can be asserted on without constructing a router —
 * `createWebHistory()` needs a `window`, and the test that used to cover this compensated by
 * re-declaring the route table inside itself, which meant it verified a copy and would have passed
 * whatever the real router said.
 *
 * `/assurance` **is** the browse surface. It was briefly a hub whose entire content was a banner
 * saying the store was fine plus a link to the node list; the banner now sits above the list, and
 * the left nav is the route to everywhere else.
 */
import type { RouteRecordRaw } from 'vue-router'
import { type AssuranceMethodSurface, ROUTE_TEMPLATES } from './artifactRoutes'

/** Where the browse surface lives, for links that need to name it. */
export const ASSURANCE_BROWSE_PATH = '/assurance'

type Loader = () => Promise<unknown>

/** The surface that *edits* an existing analysis of each method. FMEA's is a matrix rather than a
 * wizard, which is the one asymmetry: the others' wizards are the method's only surface. */
const METHOD_SURFACES: Readonly<Record<AssuranceMethodSurface, Loader>> = {
  fmea: () => import('../views/AssuranceFmeaView.vue'),
  stpa: () => import('../views/AssuranceStpaWizardView.vue'),
  grc: () => import('../views/AssuranceGrcWizardView.vue'),
  cast: () => import('../views/AssuranceCastWizardView.vue'),
  gsn: () => import('../views/AssuranceGsnWizardView.vue'),
}

/** The surface that *creates* one. The four wizards create and edit through the same component —
 * they take the analysis from the route and open blank without one — so only FMEA differs. */
const CREATE_SURFACES: Readonly<Record<AssuranceMethodSurface, Loader>> = {
  ...METHOD_SURFACES,
  fmea: () => import('../views/AssuranceFmeaWizardView.vue'),
}

/**
 * One route per method, spelled from the shared template.
 *
 * Five literal segments rather than a `:method` parameter with a dispatcher component: the surfaces
 * are genuinely different components, and a dispatcher would add an indirection whose only job is
 * to undo the parameter. The template is still the single place the shape is written.
 */
const methodRoutes = (
  template: string,
  surfaces: Readonly<Record<AssuranceMethodSurface, Loader>>,
): RouteRecordRaw[] =>
  (Object.keys(surfaces) as AssuranceMethodSurface[]).map((method) => ({
    path: template.replace(':method', method),
    component: surfaces[method],
  }))

export const assuranceRoutes: RouteRecordRaw[] = [
  { path: ASSURANCE_BROWSE_PATH, component: () => import('../views/AssuranceBrowseView.vue') },
  // `/assurance/browse` predates the browse surface being `/assurance` itself; the query carries
  // through so `?node_id=` and `?view=tree` survive the move.
  {
    path: '/assurance/browse',
    redirect: to => ({ path: ASSURANCE_BROWSE_PATH, query: to.query, hash: to.hash }),
  },
  { path: ROUTE_TEMPLATES.assuranceAnalysisList, redirect: ASSURANCE_BROWSE_PATH },
  // `new` before the analysis id: an analysis whose id were `new` would otherwise address the
  // create surface and lose. The outcome is asserted, not the ranking rule.
  ...methodRoutes(ROUTE_TEMPLATES.assuranceAnalysisCreate, CREATE_SURFACES),
  {
    path: ROUTE_TEMPLATES.assuranceAnalysisDiagram,
    component: () => import('../views/AssuranceDiagramDetailView.vue'),
  },
  ...methodRoutes(ROUTE_TEMPLATES.assuranceAnalysisMethod, METHOD_SURFACES),
  { path: ROUTE_TEMPLATES.assuranceNodeDetail, component: () => import('../views/AssuranceNodeView.vue') },
  { path: ROUTE_TEMPLATES.assuranceNodeGraph, component: () => import('../views/AssuranceGraphExploreView.vue') },
  // The exploration surface with no anchor node, the counterpart of `/graph` on the model side.
  { path: '/assurance/graph', component: () => import('../views/AssuranceGraphExploreView.vue') },
  {
    path: ROUTE_TEMPLATES.assuranceSupplyChain,
    component: () => import('../views/AssuranceSupplyChainWizardView.vue'),
  },
  // The findings surface answers two questions: every anchor's findings, and one anchor's. The
  // first addresses no particular element, so it carries no identity.
  {
    path: ROUTE_TEMPLATES.assuranceSecurityFindingsList,
    // The anchors, not the findings. `SecurityFindingsView` needs an entity id — mounted here it
    // rendered its header with an empty one and nothing else.
    component: () => import('../views/SecurityFindingsIndexView.vue'),
  },
  {
    path: ROUTE_TEMPLATES.assuranceSecurityFindings,
    component: () => import('../views/SecurityFindingsView.vue'),
  },
  {
    path: ROUTE_TEMPLATES.assuranceVulnerability,
    component: () => import('../views/VulnerabilityImpactView.vue'),
  },
  {
    path: ROUTE_TEMPLATES.assuranceBaselines,
    component: () => import('../views/AssuranceBaselinesView.vue'),
  },
  {
    path: ROUTE_TEMPLATES.assuranceDiagramList,
    component: () => import('../views/AssuranceDiagramsView.vue'),
  },
]
