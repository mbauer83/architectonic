/**
 * The node contract of `NavTree.vue`.
 *
 * Domain-agnostic by contract — a node carries its label, its badge and the route it opens, and
 * this module never imports architecture, assurance, viewpoint or ontology concepts. The shape of
 * a tree is the caller's knowledge, because the caller is the only party that knows what its
 * levels mean.
 *
 * A `.ts` module rather than an export of the SFC: helpers and tests consume this type, and typed
 * lint cannot resolve types imported from a `.vue` file into a `.ts` one — every consumer would
 * degrade to `error`-typed values and fail the unsafe-* rules.
 */
import type { RouteLocationRaw } from 'vue-router'

export interface NavTreeNode {
  /** Stable identity, unique among its siblings. */
  key: string
  label: string
  /** Short trailing annotation — a count, a method, a status. Purely presentational. */
  badge?: string
  /** Where the node navigates. A node without one is a heading that only expands. */
  to?: RouteLocationRaw
  children?: NavTreeNode[]
  /** Start collapsed. Absent means expanded — a level the reader has never seen should not
   *  arrive already hidden, unless the caller knows it is long. */
  collapsedByDefault?: boolean
}
