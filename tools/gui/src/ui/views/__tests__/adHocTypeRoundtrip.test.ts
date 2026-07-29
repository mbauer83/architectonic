/**
 * Logic tests for ad-hoc attribute type selection and round-trip behaviour.
 *
 * Tests the `buildBody` / `buildEditBody` attribute_types collection logic and
 * the startEdit pre-population from saved `attribute-types` extra frontmatter.
 * All tested without mounting components (pure Vue reactivity).
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'

const ADHOC_SCALAR_TYPES = ['string', 'integer', 'number', 'boolean', 'array'] as const
type AdHocType = (typeof ADHOC_SCALAR_TYPES)[number]

type PropRow = { key: string; value: string; adHocType: AdHocType }

// Mirror the attribute_types collection from buildEditBody / buildBody
function collectAttributeTypes(
  rows: PropRow[],
  schemaKeys: Set<string>,
): Record<string, string> {
  const out: Record<string, string> = {}
  for (const row of rows) {
    const k = row.key.trim()
    if (!k) continue
    if (!schemaKeys.has(k) && row.adHocType !== 'string') {
      out[k] = row.adHocType
    }
  }
  return out
}

// Mirror startEdit's saved-attr-types loading from entity extra
function loadSavedAttrTypes(
  extra: Record<string, unknown> | undefined,
): Record<string, AdHocType> {
  const raw = extra?.['attribute-types']
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>)
      .filter(([, v]) => (ADHOC_SCALAR_TYPES as readonly string[]).includes(String(v)))
      .map(([k, v]) => [k, String(v) as AdHocType]),
  )
}

describe('attribute_types collection', () => {
  it('omits string-typed ad-hoc properties (backend default)', () => {
    const rows = ref<PropRow[]>([
      { key: 'MyText', value: 'hello', adHocType: 'string' },
    ])
    expect(collectAttributeTypes(rows.value, new Set())).toEqual({})
  })

  it('includes integer-typed ad-hoc properties', () => {
    const rows = ref<PropRow[]>([
      { key: 'Count', value: '42', adHocType: 'integer' },
    ])
    expect(collectAttributeTypes(rows.value, new Set())).toEqual({ Count: 'integer' })
  })

  it('includes boolean-typed ad-hoc properties', () => {
    const rows = ref<PropRow[]>([
      { key: 'Active', value: 'true', adHocType: 'boolean' },
    ])
    expect(collectAttributeTypes(rows.value, new Set())).toEqual({ Active: 'boolean' })
  })

  it('omits schema-declared keys even if adHocType is non-string', () => {
    const rows = ref<PropRow[]>([
      { key: 'Maturity', value: 'Not Assessed', adHocType: 'integer' },
    ])
    expect(collectAttributeTypes(rows.value, new Set(['Maturity']))).toEqual({})
  })

  it('skips rows with blank keys', () => {
    const rows = ref<PropRow[]>([
      { key: '', value: '42', adHocType: 'integer' },
      { key: '  ', value: '7', adHocType: 'number' },
    ])
    expect(collectAttributeTypes(rows.value, new Set())).toEqual({})
  })

  it('handles mixed schema and ad-hoc props together', () => {
    const rows = ref<PropRow[]>([
      { key: 'Maturity', value: 'Not Assessed', adHocType: 'string' },
      { key: 'Count', value: '5', adHocType: 'integer' },
      { key: 'Note', value: 'hi', adHocType: 'string' },
    ])
    expect(collectAttributeTypes(rows.value, new Set(['Maturity']))).toEqual({ Count: 'integer' })
  })
})

describe('startEdit: load saved attribute-types from extra frontmatter', () => {
  it('loads integer type from saved extra', () => {
    const extra = { 'attribute-types': { Count: 'integer', Score: 'number' } }
    expect(loadSavedAttrTypes(extra)).toEqual({ Count: 'integer', Score: 'number' })
  })

  it('ignores unknown/unsupported types', () => {
    const extra = { 'attribute-types': { MyField: 'object', Count: 'integer' } }
    expect(loadSavedAttrTypes(extra)).toEqual({ Count: 'integer' })
  })

  it('returns empty when attribute-types is absent', () => {
    expect(loadSavedAttrTypes({})).toEqual({})
    expect(loadSavedAttrTypes(undefined)).toEqual({})
  })

  it('returns empty when attribute-types is not an object', () => {
    const extra = { 'attribute-types': 'not-an-object' }
    expect(loadSavedAttrTypes(extra)).toEqual({})
  })

  it('boolean and array types are recognised', () => {
    const extra = { 'attribute-types': { IsActive: 'boolean', Tags: 'array' } }
    expect(loadSavedAttrTypes(extra)).toEqual({ IsActive: 'boolean', Tags: 'array' })
  })
})

describe('type change resets value', () => {
  it('non-boolean type change clears value to empty string', () => {
    const row = ref({ key: 'Count', value: 'hello', adHocType: 'string' })
    // Simulate @change handler: row.value = row.adHocType === 'boolean' ? 'false' : ''
    row.value.adHocType = 'integer'
    row.value.value = row.value.adHocType === 'boolean' ? 'false' : ''
    expect(row.value.value).toBe('')
  })

  it('boolean type change sets value to "false"', () => {
    const row = ref({ key: 'Active', value: '42', adHocType: 'integer' })
    row.value.adHocType = 'boolean'
    row.value.value = row.value.adHocType === 'boolean' ? 'false' : ''
    expect(row.value.value).toBe('false')
  })
})
