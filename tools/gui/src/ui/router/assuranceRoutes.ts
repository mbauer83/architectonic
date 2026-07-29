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

/** Where the browse surface lives, for links that need to name it. */
export const ASSURANCE_BROWSE_PATH = '/assurance'

export const assuranceRoutes: RouteRecordRaw[] = [
  { path: ASSURANCE_BROWSE_PATH, component: () => import('../views/AssuranceBrowseView.vue') },
  // Links to the former paths are in the wild and bookmarked. Both redirect with the query intact,
  // so `?node_id=` and `?view=tree` keep working through the move.
  {
    path: '/assurance/browse',
    redirect: to => ({ path: ASSURANCE_BROWSE_PATH, query: to.query, hash: to.hash }),
  },
  {
    path: '/assurance/analyses',
    redirect: to => ({ path: ASSURANCE_BROWSE_PATH, query: to.query, hash: to.hash }),
  },
  { path: '/assurance/graph', component: () => import('../views/AssuranceGraphExploreView.vue') },
  { path: '/assurance/node/:id', component: () => import('../views/AssuranceNodeView.vue') },
  { path: '/assurance/fmea', component: () => import('../views/AssuranceFmeaView.vue') },
  { path: '/assurance/fmea/new', component: () => import('../views/AssuranceFmeaWizardView.vue') },
  { path: '/assurance/stpa', component: () => import('../views/AssuranceStpaWizardView.vue') },
  { path: '/assurance/grc', component: () => import('../views/AssuranceGrcWizardView.vue') },
  { path: '/assurance/cast', component: () => import('../views/AssuranceCastWizardView.vue') },
  { path: '/assurance/gsn', component: () => import('../views/AssuranceGsnWizardView.vue') },
  {
    path: '/assurance/supply-chain',
    component: () => import('../views/AssuranceSupplyChainWizardView.vue'),
  },
  {
    path: '/assurance/security/findings',
    component: () => import('../views/SecurityFindingsView.vue'),
  },
  {
    path: '/assurance/security/vulnerability',
    component: () => import('../views/VulnerabilityImpactView.vue'),
  },
  { path: '/assurance/baselines', component: () => import('../views/AssuranceBaselinesView.vue') },
  { path: '/assurance/diagrams', component: () => import('../views/AssuranceDiagramsView.vue') },
  { path: '/assurance/diagram', component: () => import('../views/AssuranceDiagramDetailView.vue') },
]
