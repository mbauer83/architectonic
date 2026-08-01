import { describe, it, expect } from 'vitest'
import { NO_QUARANTINE, quarantineFromSchemaInfo, quarantineHeadline } from './schemaQuarantine'
import type { EntitySchemaInfo } from '../../domain'

const info = (over: Partial<EntitySchemaInfo>): EntitySchemaInfo => ({
  artifact_type: 'collaboration',
  specialization: '',
  // `schema` is absent, not null, when no schema file declares one — the route omits what is
  // not set. Every other field is always sent.
  properties: [],
  required: [],
  descriptors: {},
  conflicts: [],
  quarantined: false,
  ...over,
})

describe('quarantineFromSchemaInfo', () => {
  it('reads the endpoint flag when present', () => {
    const result = quarantineFromSchemaInfo(info({ quarantined: true, conflicts: ['scope: string vs integer'] }))
    expect(result.quarantined).toBe(true)
    expect(result.conflicts).toEqual(['scope: string vs integer'])
  })

  it('is clean when the endpoint reports a clean pair', () => {
    expect(quarantineFromSchemaInfo(info({ quarantined: false, conflicts: [] })).quarantined).toBe(false)
  })

  it('is clean when neither the flag nor any conflict is present', () => {
    const result = quarantineFromSchemaInfo(info({}))
    expect(result.quarantined).toBe(false)
    expect(result.conflicts).toEqual([])
  })
})

describe('quarantineHeadline', () => {
  it('names the specialization when one is selected', () => {
    expect(quarantineHeadline('collaboration', 'business-collaboration'))
      .toBe('Authoring is blocked for collaboration «business-collaboration»')
  })

  it('names the bare type when none is selected', () => {
    expect(quarantineHeadline('collaboration', '')).toBe('Authoring is blocked for collaboration')
  })
})

describe('NO_QUARANTINE', () => {
  it('is the clean resting state the forms reset to', () => {
    expect(NO_QUARANTINE.quarantined).toBe(false)
    expect(NO_QUARANTINE.conflicts).toEqual([])
  })
})
