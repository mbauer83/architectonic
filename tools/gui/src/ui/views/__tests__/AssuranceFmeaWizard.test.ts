/**
 * The failure-mode wizard's step definition.
 *
 * The relation- and node-type assertions are the ones that matter most, and they exist because
 * this repository has already shipped a wizard step declaring a connection type the ontology did
 * not register: the backend rejected every edge it tried to create, and the step's completeness
 * tick could never appear. Generated vocabulary is checked here so that cannot recur silently.
 */

import { describe, expect, it } from 'vitest'
import { CONNECTION_TYPE_NAMES, ENTITY_TYPE_NAMES } from '../../../domain/types.generated'
import {
  FMEA_GUIDEWORDS,
  FMEA_STEPS,
  firstIncompleteStep,
  relationSatisfied,
  remainingGuidewords,
} from '../AssuranceFmeaWizard.helpers'
import type { WizardEdge, WizardNode } from '../AssuranceFmeaWizard.helpers'

function node(overrides: Partial<WizardNode> = {}): WizardNode {
  return { node_id: 'FMD@1', node_type: 'failure-mode', name: 'A failure', ...overrides }
}

describe('FMEA_STEPS', () => {
  it('runs Component → Failure modes → Effects → Causes → Controls → Factors → Review', () => {
    expect(FMEA_STEPS.map((s) => s.key)).toEqual([
      'component', 'failure-modes', 'effects', 'causes', 'controls', 'factors', 'review',
    ])
  })

  it('declares only relations the ontology registers, so no step can request an unknown edge', () => {
    const declared = FMEA_STEPS.flatMap((s) => (s.relation ? [s.relation.connType] : []))

    expect(declared.length).toBeGreaterThan(0)
    for (const connType of declared) {
      expect(CONNECTION_TYPE_NAMES).toContain(connType)
    }
  })

  it('declares only node types the ontology registers', () => {
    const declared = FMEA_STEPS
      .flatMap((s) => [s.nodeType, ...(s.relation ? [s.relation.targetType] : [])])
      .filter((t) => t !== '')

    for (const nodeType of declared) {
      expect(ENTITY_TYPE_NAMES).toContain(nodeType)
    }
  })

  it('links an effect to a hazard rather than to a loss', () => {
    // Straight to a loss would bypass the hazard spine and start a second consequence vocabulary.
    const effects = FMEA_STEPS.find((s) => s.key === 'effects')

    expect(effects?.relation).toEqual({
      connType: 'leads-to', targetType: 'hazard', targetLabel: 'hazard',
    })
  })

  it('points detection from the control at the failure mode', () => {
    const controls = FMEA_STEPS.find((s) => s.key === 'controls')

    expect(controls?.relation?.connType).toBe('detects')
    expect(controls?.relation?.targetType).toBe('failure-mode')
  })

  it('gives every step that creates something a guidance topic', () => {
    for (const step of FMEA_STEPS.filter((s) => s.nodeType !== '')) {
      expect(step.guidanceTopic).not.toBe('')
    }
  })

  it('uses the shared guideword vocabulary rather than a list of its own', () => {
    expect(FMEA_GUIDEWORDS).toHaveLength(5)
    expect(FMEA_GUIDEWORDS).toContain('no-function')
  })
})

describe('what is left to do', () => {
  it('a component with nothing recorded still has all five guidewords', () => {
    expect(remainingGuidewords([])).toHaveLength(5)
  })

  it('a recorded guideword drops off the list', () => {
    const remaining = remainingGuidewords([node({ failure_type: 'no-function' })])

    expect(remaining).not.toContain('no-function')
    expect(remaining).toHaveLength(4)
  })

  it('nodes of other types do not count as coverage', () => {
    const remaining = remainingGuidewords([node({ node_type: 'hazard', failure_type: 'no-function' })])

    expect(remaining).toHaveLength(5)
  })
})

describe('a relation is satisfied only by the relation it asks for', () => {
  const relation = { connType: 'leads-to', targetType: 'hazard', targetLabel: 'hazard' }

  it('is satisfied by an edge of that type from that node', () => {
    const edges: WizardEdge[] = [{ source_id: 'FMD@1', target_id: 'HAZ@1', conn_type: 'leads-to' }]

    expect(relationSatisfied(node(), relation, edges)).toBe(true)
  })

  it('is not satisfied by a different relation', () => {
    const edges: WizardEdge[] = [{ source_id: 'FMD@1', target_id: 'ACN@1', conn_type: 'derives' }]

    expect(relationSatisfied(node(), relation, edges)).toBe(false)
  })

  it('is not satisfied by another node’s edge', () => {
    const edges: WizardEdge[] = [{ source_id: 'FMD@2', target_id: 'HAZ@1', conn_type: 'leads-to' }]

    expect(relationSatisfied(node(), relation, edges)).toBe(false)
  })

  it('a step declaring no relation is always satisfied', () => {
    expect(relationSatisfied(node(), undefined, [])).toBe(true)
  })
})

describe('where a returning author lands', () => {
  it('on failure modes when nothing has been recorded', () => {
    expect(firstIncompleteStep([], [])).toBe('failure-modes')
  })

  it('still on failure modes while guidewords remain', () => {
    expect(firstIncompleteStep([node({ failure_type: 'no-function' })], [])).toBe('failure-modes')
  })

  it('on effects once every guideword is recorded but some has no hazard', () => {
    const nodes = FMEA_GUIDEWORDS.map((slug, i) =>
      node({ node_id: `FMD@${i}`, failure_type: slug }))

    expect(firstIncompleteStep(nodes, [])).toBe('effects')
  })

  it('on review once every failure mode leads to a hazard', () => {
    const nodes = FMEA_GUIDEWORDS.map((slug, i) =>
      node({ node_id: `FMD@${i}`, failure_type: slug }))
    const edges: WizardEdge[] = nodes.map((n) => ({
      source_id: n.node_id, target_id: 'HAZ@1', conn_type: 'leads-to',
    }))

    expect(firstIncompleteStep(nodes, edges)).toBe('review')
  })
})
