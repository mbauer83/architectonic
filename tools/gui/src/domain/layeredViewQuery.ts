/**
 * Ad-hoc (never saved) query construction for the layered-exploration and
 * motivation-support flows: "pick some roots, include their indirectly connected
 * neighbors of a given kind, render only that population plus derived arrows" — no
 * saved viewpoint definition, no YAML/formula input, built entirely on the existing
 * `ExecutableQueryNode` grammar and executed via `query` (not `slug`) against the
 * already-built execution pipeline.
 */

import {
  type ExecutableQueryNode, type GroupNode, literalValue, mkGroup, mkNeighborInclusion, mkQuery, nextNodeId,
} from './viewpointCriteria'

export interface LayeredViewParams {
  /** Explicit root entity ids (the "by name/id" selection mode) — mutually exclusive
   * with `rootCriteria`; ignored when `rootCriteria` is given. */
  readonly rootEntityIds: readonly string[]
  /** The "by criteria" selection mode — takes precedence over `rootEntityIds` when set. */
  readonly rootCriteria: GroupNode | null
  /** What kind of indirectly-connected neighbor to pull in (e.g. domain = technology,
   * or a motivation flow's process/function/event/service/application type list). */
  readonly neighborCriteria: GroupNode
  readonly includePotential: boolean
  /** Backend floor is 2 (a single hop has nothing to derive) — callers should not offer
   * a lower value in their own hop-bound control. */
  readonly maxHops: number
}

const rootEntityIdsCriteria = (ids: readonly string[]): GroupNode => {
  const group = mkGroup('entity')
  group.children = [{
    kind: 'condition', id: nextNodeId(), attribute: 'id', comparator: 'in', value: literalValue([...ids]), negate: false,
  }]
  return group
}

/** Builds the ad-hoc query: selected roots (by id or criteria) as the primary population,
 * one `traversal: derived` neighbor inclusion for the requested neighbor kind, and
 * `connections.traversal: both` so both the roots' own real connections and every derived
 * witness/relationship arrive in the same execution result. */
export const buildLayeredViewQuery = (params: LayeredViewParams): ExecutableQueryNode => {
  const query = mkQuery()
  query.entityCriteria = params.rootCriteria ?? rootEntityIdsCriteria(params.rootEntityIds)

  const inclusion = mkNeighborInclusion()
  inclusion.connectionCriteria = null
  inclusion.neighborCriteria = params.neighborCriteria
  inclusion.traversal = 'derived'
  inclusion.includePotential = params.includePotential
  inclusion.maxHops = params.maxHops
  query.includeConnected = [inclusion]

  query.connections.traversal = 'both'
  query.connections.includePotential = params.includePotential
  query.connections.maxHops = params.maxHops

  return query
}
