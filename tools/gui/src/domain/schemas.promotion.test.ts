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
  // The five the plan always sends. Four were optional here and two were absent from the schema
  // altogether — and `viewpoint_dependencies` and `missing_dependencies` are the two that can leave
  // the enterprise repository broken, so a fixture that omits them proves nothing about a real plan.
  structural_closure: [],
  group_mapping: [],
  available_enterprise_groups: [],
  viewpoint_dependencies: [],
  missing_dependencies: [],
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

  it('refuses a plan missing a list, rather than defaulting it to empty', () => {
    /* This used to default `structural_closure` to `[]` "for plans from older backends". There are no
       older backends — the wire is versioned with the code — and the default made "no junction needs
       closing" indistinguishable from "closure was never computed", in the one payload whose whole job
       is to be read before someone agrees to it. */
    const withoutClosure: Record<string, unknown> = { ...basePlan }
    delete withoutClosure['structural_closure']

    expect(() => Schema.decodeUnknownSync(PromotionPlanSchema)(withoutClosure)).toThrow()
  })
})
