import { describe, expect, it } from 'vitest'
import { reconcileRowsWithSchema, rowsFromSchema, type PropertyRow } from '../schemaPropertyRows'

const row = (key: string, value = '', adHocType: PropertyRow['adHocType'] = 'string'): PropertyRow => ({
  key,
  value,
  adHocType,
})

describe('rowsFromSchema', () => {
  it('builds one row per schema property with defaults applied', () => {
    const rows = rowsFromSchema({
      properties: ['scope', 'cadence'],
      descriptors: { cadence: { default: 'weekly' } },
    })
    expect(rows).toEqual([row('scope'), row('cadence', 'weekly')])
  })
})

describe('reconcileRowsWithSchema', () => {
  it('adds rows for specialization-contributed attributes', () => {
    const next = reconcileRowsWithSchema([row('scope', 'team')], ['scope'], {
      properties: ['scope', 'cadence'],
      descriptors: { cadence: { default: 'weekly' } },
    })
    expect(next).toEqual([row('scope', 'team'), row('cadence', 'weekly')])
  })

  it('keeps user-entered values on schema rows across schema changes', () => {
    const next = reconcileRowsWithSchema([row('scope', 'team'), row('cadence', 'daily')], ['scope', 'cadence'], {
      properties: ['scope', 'cadence'],
      descriptors: {},
    })
    expect(next).toEqual([row('scope', 'team'), row('cadence', 'daily')])
  })

  it('drops empty rows that only existed in the previous schema', () => {
    const next = reconcileRowsWithSchema([row('scope', 'team'), row('cadence', '')], ['scope', 'cadence'], {
      properties: ['scope'],
      descriptors: {},
    })
    expect(next).toEqual([row('scope', 'team')])
  })

  it('preserves previous-schema rows the user filled in as carried rows', () => {
    const next = reconcileRowsWithSchema([row('scope', 'team'), row('cadence', 'daily')], ['scope', 'cadence'], {
      properties: ['scope'],
      descriptors: {},
    })
    expect(next).toEqual([row('scope', 'team'), row('cadence', 'daily')])
  })

  it('always keeps ad-hoc rows the user added by hand, even when empty', () => {
    const next = reconcileRowsWithSchema([row('scope', ''), row('custom', '', 'integer')], ['scope'], {
      properties: ['scope', 'cadence'],
      descriptors: {},
    })
    expect(next).toEqual([row('scope'), row('cadence'), row('custom', '', 'integer')])
  })
})
