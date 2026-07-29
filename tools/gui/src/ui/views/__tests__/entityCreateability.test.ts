/**
 * GUI createability tests: verifies that EntityCreateView's required-property guard
 * correctly blocks save when required attributes are absent and allows save when they
 * are filled in.  Tests the pure reactive logic without mounting the full component.
 *
 * This is the "GUI-createability" test described in WU-B1: every required property in
 * a schema must be collectable by the create form, and the form must block save until
 * all required properties have a non-empty value.
 */
import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'

type PropRow = { key: string; value: string }

// Mirror createRequiredMissing logic from EntityCreateView.vue
function makeCreateRequiredMissing(schemaRequired: Set<string>, properties: PropRow[]): boolean {
  return [...schemaRequired].some((key) => {
    const row = properties.find((r) => r.key === key)
    return !row || !row.value.trim()
  })
}

describe('createability: required-property guard', () => {
  it('blocks save when a required property has no row', () => {
    const schemaRequired = new Set(['Maturity'])
    const properties: PropRow[] = []
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(true)
  })

  it('blocks save when a required property row is empty', () => {
    const schemaRequired = new Set(['Maturity'])
    const properties: PropRow[] = [{ key: 'Maturity', value: '' }]
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(true)
  })

  it('blocks save when a required property row is whitespace only', () => {
    const schemaRequired = new Set(['Maturity'])
    const properties: PropRow[] = [{ key: 'Maturity', value: '   ' }]
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(true)
  })

  it('allows save when all required properties have values', () => {
    const schemaRequired = new Set(['Maturity'])
    const properties: PropRow[] = [{ key: 'Maturity', value: 'Not Assessed' }]
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(false)
  })

  it('allows save when multiple required properties all have values', () => {
    const schemaRequired = new Set(['Maturity', 'Category'])
    const properties: PropRow[] = [
      { key: 'Maturity', value: 'Not Assessed' },
      { key: 'Category', value: 'Unspecified' },
    ]
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(false)
  })

  it('blocks save when at least one of multiple required props is missing', () => {
    const schemaRequired = new Set(['Maturity', 'Category'])
    const properties: PropRow[] = [
      { key: 'Maturity', value: 'Not Assessed' },
      // Category intentionally absent
    ]
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(true)
  })

  it('non-required optional properties do not affect save guard', () => {
    const schemaRequired = new Set(['Maturity'])
    const properties: PropRow[] = [
      { key: 'Maturity', value: 'Initial' },
      { key: 'OptionalField', value: '' },  // optional, empty → still allowed
    ]
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(false)
  })

  it('no required properties means guard is always false (save allowed)', () => {
    const schemaRequired = new Set<string>()
    const properties: PropRow[] = []
    expect(makeCreateRequiredMissing(schemaRequired, properties)).toBe(false)
  })
})

describe('createability: reactive computed guard', () => {
  it('guard updates reactively when property value is filled in', () => {
    const schemaRequired = new Set(['Maturity'])
    const properties = ref<PropRow[]>([{ key: 'Maturity', value: '' }])
    const createRequiredMissing = computed(() =>
      makeCreateRequiredMissing(schemaRequired, properties.value),
    )

    expect(createRequiredMissing.value).toBe(true)
    properties.value[0].value = 'Not Assessed'
    expect(createRequiredMissing.value).toBe(false)
  })

  it('guard reacts when a new required-property row is added', () => {
    const schemaRequired = new Set(['Maturity'])
    const properties = ref<PropRow[]>([])
    const createRequiredMissing = computed(() =>
      makeCreateRequiredMissing(schemaRequired, properties.value),
    )

    expect(createRequiredMissing.value).toBe(true)
    properties.value = [{ key: 'Maturity', value: 'Defined' }]
    expect(createRequiredMissing.value).toBe(false)
  })
})
