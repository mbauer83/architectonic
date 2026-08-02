import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { assuranceRoutes } from './assuranceRoutes'
import { modelRoutes } from './modelRoutes'

/**
 * Matches everything left. Without it an unserved address renders the chrome and an empty <main>,
 * which reads as a broken page rather than a wrong one. Declared apart from the two area tables so
 * a check over "the addresses this application serves" can exclude it: it matches every string, and
 * counting it would make every dead link look live.
 */
export const notFoundRoute: RouteRecordRaw = {
  path: '/:pathMatch(.*)*',
  component: () => import('../views/NotFoundView.vue'),
}

export const router = createRouter({
  history: createWebHistory(),
  // Assurance is enabled-gated and separate from the model nav; the catch-all is last, so a real
  // address is never shadowed by it.
  routes: [...modelRoutes, ...assuranceRoutes, notFoundRoute],
})
