import { describe, expect, it } from 'vitest'
import {
  GSN_STEPS,
  completenessFailures,
  publicationBody,
  sourceBindings,
  type GsnDiagramEntities,
} from '../AssuranceGsnWizard.helpers'

const entities: GsnDiagramEntities = {
  nodes: [
    { node_id: 'G1', name: 'Claim', gsn_type: 'goal', source_assurance_ids: ['L@1', 'H@1'] },
    { node_id: 'C1', name: 'Context', gsn_type: 'context' },
  ],
  edges: [{ source_id: 'G1', target_id: 'C1', conn_type: 'in-context-of' }],
}

describe('GSN wizard helpers', () => {
  it('uses the required dual-home flow', () => {
    expect(GSN_STEPS.map((step) => step.key)).toEqual([
      'draft', 'destination', 'preview', 'bindings', 'completeness',
    ])
  })

  it('builds source bindings without inventing architecture back-references', () => {
    expect(sourceBindings(entities)).toEqual([
      { assurance_node_id: 'L@1', gsn_node_id: 'G1' },
      { assurance_node_id: 'H@1', gsn_node_id: 'G1' },
    ])
  })

  it('builds the publication audit body', () => {
    expect(publicationBody('AN@1', 'GSN@1.case', entities)).toEqual({
      analysis_id: 'AN@1',
      diagram_id: 'GSN@1.case',
      source_bindings: sourceBindings(entities),
    })
  })

  it('summarises failed completeness checks', () => {
    expect(completenessFailures({
      passed: false,
      checks: {
        evidence: { passed: false, gap_count: 2 },
        losses: { passed: true, gap_count: 0 },
      },
    })).toEqual([{ key: 'evidence', gapCount: 2 }])
  })
})
