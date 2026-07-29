import { describe, it, expect } from 'vitest'
import { NO_QUARANTINE, quarantineFromSchemaInfo, quarantineHeadline } from './schemaQuarantine'
import type { EntitySchemaInfo } from '../../domain'

const info = (over: Partial<EntitySchemaInfo>): EntitySchemaInfo => ({
  artifact_type: 'collaboration',
  specialization: '',
  schema: null,
  properties: [],
  required: [],
  descriptors: {},
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

  it('falls back to the conflict list when the flag is absent', () => {
    // A backend predating the derived flag still returns the conflicts it derives from,
    // so an ambiguous pair must not be reported as clean.
    expect(quarantineFromSchemaInfo(info({ conflicts: ['scope: string vs integer'] })).quarantined).toBe(true)
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
