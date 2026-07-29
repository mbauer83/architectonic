/**
 * Pure helpers for the layered-exploration / motivation-support view: turning an ad-hoc
 * execution result plus the ephemeral candidate-review state into a renderable node/edge
 * set, and the two presentation presets the builder panel offers.
 */

import type { ConnectionItemSummary, EntityItemSummary } from '../../domain'
import { acceptedConnections, isDerivedConnection, type CandidateReviewState } from '../../domain/derivedCandidateReview'
import { mkCondition, mkGroup, literalValue, type GroupNode } from '../../domain/viewpointCriteria'

export type LayeredPreset = 'layered' | 'motivation-support'

export interface PresetDefaults {
  readonly label: string
  readonly rootLabel: string
  readonly neighborLabel: string
  readonly neighborCriteria: () => GroupNode
}

const technologyDomainCriteria = (): GroupNode => {
  const group = mkGroup('entity')
  group.children = [{ ...mkCondition('domain', 'eq'), value: literalValue('technology') }]
  return group
}

const motivationSupportCriteria = (): GroupNode => {
  const group = mkGroup('entity')
  group.children = [{
    ...mkCondition('type', 'in'),
    value: literalValue(['business-process', 'business-function', 'business-event', 'application-service', 'business-service']),
  }]
  return group
}

export const PRESET_DEFAULTS: Record<LayeredPreset, PresetDefaults> = {
  layered: {
    label: 'Layered view', rootLabel: 'Processes / services', neighborLabel: 'Supporting technology',
    neighborCriteria: technologyDomainCriteria,
  },
  'motivation-support': {
    label: 'Motivation support', rootLabel: 'Requirement / motivation element', neighborLabel: 'Supporting elements',
    neighborCriteria: motivationSupportCriteria,
  },
}

export interface RenderNode {
  readonly id: string
  readonly label: string
  readonly type: string
}

export interface RenderEdge {
  readonly source: string
  readonly target: string
  readonly connType: string
  readonly certainty: ConnectionItemSummary['certainty']
}

/** The rendered population is every entity in the result plus every connection the
 * candidate-review state currently accepts — a rejected derived connection is withheld,
 * but its endpoints stay rendered if reachable some other way (never silently orphaned by
 * this helper; an isolated node is a legitimate outcome the caller can see, not hidden). */
export const buildRenderGraph = (
  entities: readonly EntityItemSummary[],
  connections: readonly ConnectionItemSummary[],
  review: CandidateReviewState,
): { nodes: readonly RenderNode[]; edges: readonly RenderEdge[] } => ({
  nodes: entities.map((entity) => ({ id: entity.id, label: entity.name, type: entity.type })),
  edges: acceptedConnections(review, connections).map((connection) => ({
    source: connection.source, target: connection.target, connType: connection.type, certainty: connection.certainty,
  })),
})

export const derivedCandidates = (connections: readonly ConnectionItemSummary[]): readonly ConnectionItemSummary[] =>
  connections.filter(isDerivedConnection)
