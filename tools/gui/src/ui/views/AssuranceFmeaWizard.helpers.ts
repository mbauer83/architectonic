// Pure helpers for the failure-mode wizard — unit-testable without a DOM.

import { FAILURE_GUIDEWORD_SLUGS } from '../lib/failureGuidewords'

export interface FmeaRelation {
  connType: string
  targetType: string
  targetLabel: string
}

export interface FmeaStep {
  key: string
  label: string
  /** Assurance node_type created in this step ('' for steps that create nothing). */
  nodeType: string
  /** assurance_guidance topic for the step's coaching panel. */
  guidanceTopic: string
  /** Optional outgoing relation this step's nodes should declare (drives completeness). */
  relation?: FmeaRelation
}

/**
 * Component → Failure modes → Effects → Causes → Controls → Factors → Review.
 *
 * The first step creates nothing: it picks the architecture element the rest of the walk is about.
 * Effects, causes and controls each declare the relation that closes their part of the chain, and
 * every one of those relations is a type the ontology registers — asserted by the same test that
 * covers the other wizard, because a wizard once declared a relation that did not exist and its
 * step could not link anything at all.
 */
export const FMEA_STEPS: FmeaStep[] = [
  { key: 'component', label: 'Component', nodeType: '', guidanceTopic: 'fmea-failure-modes' },
  {
    key: 'failure-modes', label: 'Failure modes',
    nodeType: 'failure-mode', guidanceTopic: 'fmea-failure-modes',
  },
  {
    key: 'effects', label: 'Effects', nodeType: 'failure-mode', guidanceTopic: 'fmea-effects',
    relation: { connType: 'leads-to', targetType: 'hazard', targetLabel: 'hazard' },
  },
  {
    key: 'causes', label: 'Causes', nodeType: 'loss-scenario', guidanceTopic: 'fmea-causes',
    relation: { connType: 'explains', targetType: 'failure-mode', targetLabel: 'failure mode' },
  },
  {
    key: 'controls', label: 'Controls',
    nodeType: 'assurance-constraint', guidanceTopic: 'fmea-controls',
    relation: { connType: 'detects', targetType: 'failure-mode', targetLabel: 'failure mode' },
  },
  { key: 'factors', label: 'Factors', nodeType: '', guidanceTopic: 'fmea-factors' },
  { key: 'review', label: 'Review', nodeType: '', guidanceTopic: '' },
]

export const FMEA_GUIDEWORDS = FAILURE_GUIDEWORD_SLUGS

export interface WizardNode {
  node_id: string
  node_type: string
  name: string
  failure_type?: string
}

export interface WizardEdge {
  source_id: string
  target_id: string
  conn_type: string
}

/** Whether `node` already declares the step's relation. */
export function relationSatisfied(
  node: WizardNode,
  relation: FmeaRelation | undefined,
  edges: WizardEdge[],
): boolean {
  if (!relation) return true
  return edges.some((e) => e.source_id === node.node_id && e.conn_type === relation.connType)
}

/**
 * Which guidewords this component still has no failure mode for.
 *
 * The wizard's job is to make a component's five cells finishable in one sitting, so what it shows
 * is what remains — not a count of what has been done.
 */
export function remainingGuidewords(nodes: WizardNode[]): string[] {
  const covered = new Set(
    nodes.filter((n) => n.node_type === 'failure-mode').map((n) => n.failure_type ?? ''),
  )
  return FMEA_GUIDEWORDS.filter((slug) => !covered.has(slug))
}

/** The step a returning author should land on: the first with anything left to do. */
export function firstIncompleteStep(nodes: WizardNode[], edges: WizardEdge[]): string {
  if (!nodes.some((n) => n.node_type === 'failure-mode')) return 'failure-modes'
  if (remainingGuidewords(nodes).length) return 'failure-modes'
  const effects = FMEA_STEPS.find((s) => s.key === 'effects')
  const unlinked = nodes
    .filter((n) => n.node_type === 'failure-mode')
    .some((n) => !relationSatisfied(n, effects?.relation, edges))
  return unlinked ? 'effects' : 'review'
}
