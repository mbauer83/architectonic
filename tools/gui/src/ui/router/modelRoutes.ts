/**
 * The model area's routes, as data.
 *
 * Split out of `index.ts` for the reason `assuranceRoutes` was: importing that module builds a
 * router, `createWebHistory()` needs a `window`, and a check over the served address space then
 * cannot run in a node test at all. `pathTargetPolicy` needs exactly that address space in order to
 * tell a live in-app link from a dead one.
 */
import type { RouteRecordRaw } from 'vue-router'
import { ROUTE_TEMPLATES } from './artifactRoutes'
import HomeView from '../views/HomeView.vue'
import EntitiesView from '../views/EntitiesView.vue'
import EntityDetailView from '../views/EntityDetailView.vue'
import EntityCreateView from '../views/EntityCreateView.vue'
import SearchView from '../views/SearchView.vue'
import DiagramsView from '../views/DiagramsView.vue'
import DiagramDetailView from '../views/DiagramDetailView.vue'
import CreateDiagramView from '../views/CreateDiagramView.vue'
import GraphExploreView from '../views/GraphExploreView.vue'
import EditDiagramView from '../views/EditDiagramView.vue'
import PromoteView from '../views/PromoteView.vue'

export const modelRoutes: RouteRecordRaw[] = [
  { path: '/', component: HomeView },
  // Engagement repo routes
  { path: ROUTE_TEMPLATES.entityList, component: EntitiesView },
  // Literal siblings before the identifier route: an entity whose id were `new` or `groups`
  // would otherwise address the create or the group surface, and lose.
  { path: ROUTE_TEMPLATES.entityCreate, component: EntityCreateView },
  {
    path: ROUTE_TEMPLATES.entityGroups,
    component: () => import('../views/GroupManagementView.vue'),
    props: () => ({ axis: 'model-project' }),
  },
  { path: ROUTE_TEMPLATES.entityDetail, component: EntityDetailView },
  { path: ROUTE_TEMPLATES.entityGraph, component: GraphExploreView },
  // The same surface unanchored: a viewpoint's whole population rather than one entity's
  // neighbourhood. No identity, so nothing to put in the path.
  { path: ROUTE_TEMPLATES.graphExplore, component: GraphExploreView },
  { path: ROUTE_TEMPLATES.documentList, component: () => import('../views/DocumentsView.vue') },
  { path: ROUTE_TEMPLATES.documentCreate, component: () => import('../views/DocumentCreateView.vue') },
  {
    path: ROUTE_TEMPLATES.documentGroups,
    component: () => import('../views/GroupManagementView.vue'),
    props: () => ({ axis: 'document-collection' }),
  },
  { path: ROUTE_TEMPLATES.documentDetail, component: () => import('../views/DocumentDetailView.vue') },
  { path: '/search', component: SearchView },
  { path: ROUTE_TEMPLATES.diagramList, component: DiagramsView },
  {
    path: ROUTE_TEMPLATES.diagramGroups,
    component: () => import('../views/GroupManagementView.vue'),
    props: () => ({ axis: 'diagram-collection' }),
  },
  { path: ROUTE_TEMPLATES.diagramCreate, component: CreateDiagramView },
  { path: ROUTE_TEMPLATES.diagramDetail, component: DiagramDetailView },
  { path: ROUTE_TEMPLATES.diagramEdit, component: EditDiagramView },
  // A matrix is a diagram of the matrix kind, and its authoring surfaces are the kind-specific
  // projection of it — so they address `/matrices`, which has no detail route of its own.
  { path: ROUTE_TEMPLATES.matrixCreate, component: () => import('../views/CreateMatrixView.vue') },
  { path: ROUTE_TEMPLATES.matrixEdit, component: () => import('../views/EditMatrixView.vue') },
  { path: '/graph/layered', component: () => import('../views/LayeredExplorationView.vue') },
  { path: ROUTE_TEMPLATES.viewpointList, component: () => import('../views/ViewpointsManagementView.vue') },
  { path: ROUTE_TEMPLATES.viewpointQuery, component: () => import('../views/EphemeralViewpointQueryView.vue') },
  { path: ROUTE_TEMPLATES.viewpointCreate, component: () => import('../views/ViewpointsManagementView.vue') },
  { path: ROUTE_TEMPLATES.viewpointEdit, component: () => import('../views/ViewpointsManagementView.vue') },
  { path: ROUTE_TEMPLATES.viewpointMatrix, component: () => import('../views/ViewpointMatrixView.vue') },
  { path: ROUTE_TEMPLATES.viewpointDiagram, component: () => import('../views/ViewpointDiagramView.vue') },
  // Legacy tier-first deep links → faceted routes (query + hash preserved)
  {
    path: '/global/entities',
    redirect: to => ({ path: '/entities', query: { ...to.query, tier: 'enterprise' }, hash: to.hash }),
  },
  {
    path: '/global/diagrams',
    redirect: to => ({ path: '/diagrams', query: { ...to.query, tier: 'enterprise' }, hash: to.hash }),
  },
  { path: '/global/search', redirect: '/search' },
  // Promotion
  { path: '/promote', component: PromoteView },
  // Guided modeling wizard
  { path: '/model/wizard', component: () => import('../views/ModelWizardView.vue') },
]
