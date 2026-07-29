import { describe, expect, it } from 'vitest'
import { Schema } from 'effect'
import { PromotionPlanSchema } from './schemas/promotion'

const basePlan = {
  entity_id: 'REQ@1.Abc123.sample',
  entities_to_add: [],
  conflicts: [],
  connection_ids: [],
  already_in_enterprise: [],
  warnings: [],
  documents_to_add: [],
  diagrams_to_add: [],
  doc_conflicts: [],
  diagram_conflicts: [],
  schema_errors: [],
}

describe('PromotionPlanSchema structural closure', () => {
  it('decodes a plan with closure requirements (junction and grouping kinds)', () => {
    const plan = Schema.decodeUnknownSync(PromotionPlanSchema)({
      ...basePlan,
      structural_closure: [
        {
          entity_id: 'JNO@1.Jn.junction',
          entity_name: 'Either',
          kind: 'junction',
          missing: [{ artifact_id: 'REQ@1.R1.req', name: 'First', artifact_type: 'requirement' }],
        },
        {
          entity_id: 'GRP@1.Gr.grouping',
          entity_name: 'Feature',
          kind: 'grouping',
          missing: [{ artifact_id: 'APP@1.M1.member', name: 'Member', artifact_type: 'application-component' }],
        },
      ],
    })
    expect(plan.structural_closure).toHaveLength(2)
    expect(plan.structural_closure[0].kind).toBe('junction')
    expect(plan.structural_closure[1].missing[0].name).toBe('Member')
  })

  it('defaults to an empty closure list for plans from older backends', () => {
    const plan = Schema.decodeUnknownSync(PromotionPlanSchema)(basePlan)
    expect(plan.structural_closure).toEqual([])
  })
})
