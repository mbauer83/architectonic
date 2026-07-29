import { describe, it, expect } from 'vitest'
import { connectionMetadataSchema } from '../specializationOptions'
import type { AuthoringGuidance, ConnectionMetadataSchema, SpecializationGuidance } from '../../../domain'

const block = (over: Partial<ConnectionMetadataSchema> = {}): ConnectionMetadataSchema => ({
  schema: {},
  properties: [],
  required: [],
  descriptors: {},
  conflicts: [],
  quarantined: false,
  ...over,
})

const spec = (slug: string, metadata_schema?: ConnectionMetadataSchema): SpecializationGuidance => ({
  slug, name: slug, description: '', create_when: '', never_create_when: '', metadata_schema,
})

const guidance: AuthoringGuidance = {
  connection_types: [
    {
      name: 'archimate-assignment',
      metadata_schema: block({ properties: ['cadence'], descriptors: { cadence: { type: 'string' } } }),
      specializations: [
        spec('responsibility-assignment', block({
          properties: ['cadence', 'owner'],
          required: ['owner'],
          descriptors: { cadence: { type: 'string' }, owner: { type: 'string' } },
        })),
        spec('behavior-assignment'),
      ],
    },
    { name: 'archimate-flow', specializations: [spec('deployment-flow')] },
  ],
}

describe('connectionMetadataSchema', () => {
  it('returns the type-level schema when no specialization is selected', () => {
    expect(connectionMetadataSchema(guidance, 'archimate-assignment', '')?.properties).toEqual(['cadence'])
  })

  it('returns the specialization\'s merged schema when one is selected', () => {
    const result = connectionMetadataSchema(guidance, 'archimate-assignment', 'responsibility-assignment')
    expect(result?.properties).toEqual(['cadence', 'owner'])
    expect(result?.required).toEqual(['owner'])
  })

  it('falls back to the type-level schema for a specialization that carries none', () => {
    const result = connectionMetadataSchema(guidance, 'archimate-assignment', 'behavior-assignment')
    expect(result?.properties).toEqual(['cadence'])
  })

  it('is null when the connection type carries no schema at all', () => {
    // An older backend, or one with no repository root: render no typed fields rather
    // than inventing an empty schema the operator could "fill in".
    expect(connectionMetadataSchema(guidance, 'archimate-flow', 'deployment-flow')).toBeNull()
  })

  it('is null for an unknown connection type', () => {
    expect(connectionMetadataSchema(guidance, 'archimate-triggering', '')).toBeNull()
  })

  it('is null when no guidance has loaded yet', () => {
    expect(connectionMetadataSchema(null, 'archimate-assignment', '')).toBeNull()
  })

  it('surfaces quarantine from the selected pair', () => {
    const quarantined: AuthoringGuidance = {
      connection_types: [{
        name: 'archimate-serving',
        specializations: [spec('critical-serving', block({
          quarantined: true, conflicts: ["Conflicting definitions for attribute 'Score'"],
        }))],
      }],
    }
    const result = connectionMetadataSchema(quarantined, 'archimate-serving', 'critical-serving')
    expect(result?.quarantined).toBe(true)
    expect(result?.conflicts).toHaveLength(1)
  })
})
