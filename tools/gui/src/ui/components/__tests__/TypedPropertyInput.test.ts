/**
 * Typed-attribute validation for the schema-driven forms.
 *
 * `attributeValidationError` is the source of truth for the client-side mirroring of what the
 * write path enforces, and it is what this exercises. It used to be re-implemented here, under a
 * comment saying it was a mirror — so the copy agreed with the component only until one of them
 * changed, and adding format, length and pattern checks to the component changed nothing here.
 */
import { describe, it, expect } from 'vitest'
import { ref, computed, type Ref } from 'vue'
import type { EntityAttributeDescriptor } from '../../../domain'
import { attributeValidationError } from '../../lib/attributeValidation'

function makeValidationError(
  modelValue: Ref<string>,
  descriptor: EntityAttributeDescriptor,
  required: boolean,
) {
  return computed(() => attributeValidationError(descriptor, modelValue.value, required))
}

describe('TypedPropertyInput — enum validation', () => {
  const descriptor: EntityAttributeDescriptor = {
    type: 'string',
    enum: ['Must', 'Should', 'Could', "Won't"],
  }

  it('returns null when value is a valid enum member', () => {
    const val = ref('Must')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })

  it('returns error message when value is not in enum', () => {
    const val = ref('Unknown')
    expect(makeValidationError(val, descriptor, false).value).toContain('Must be one of')
  })

  it('returns null when value is empty and not required', () => {
    const val = ref('')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })

  it('returns Required when value is empty and required', () => {
    const val = ref('')
    expect(makeValidationError(val, descriptor, true).value).toBe('Required')
  })
})

describe('TypedPropertyInput — integer validation', () => {
  const descriptor: EntityAttributeDescriptor = {
    type: 'integer',
    constraints: { minimum: 0, maximum: 100 },
  }

  it('returns null for a valid integer string', () => {
    const val = ref('42')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })

  it('returns error for non-integer input', () => {
    const val = ref('abc')
    expect(makeValidationError(val, descriptor, false).value).toBe('Must be a whole number')
  })

  it('returns error for a decimal input', () => {
    const val = ref('3.14')
    expect(makeValidationError(val, descriptor, false).value).toBe('Must be a whole number')
  })

  it('accepts negative integers', () => {
    const val = ref('-5')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })
})

describe('TypedPropertyInput — number validation', () => {
  const descriptor: EntityAttributeDescriptor = { type: 'number' }

  it('returns null for a valid decimal string', () => {
    const val = ref('3.14')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })

  it('returns error for non-numeric input', () => {
    const val = ref('not-a-number')
    expect(makeValidationError(val, descriptor, false).value).toBe('Must be a number')
  })

  it('returns null for integer-style number', () => {
    const val = ref('42')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })
})

describe('TypedPropertyInput — required guard', () => {
  const descriptor: EntityAttributeDescriptor = { type: 'string' }

  it('blocks when value is whitespace-only and required', () => {
    const val = ref('   ')
    expect(makeValidationError(val, descriptor, true).value).toBe('Required')
  })

  it('allows empty value when not required', () => {
    const val = ref('')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })
})

describe('TypedPropertyInput — boolean type (no text validation)', () => {
  const descriptor: EntityAttributeDescriptor = { type: 'boolean' }

  it('returns null for "true"', () => {
    const val = ref('true')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })

  it('returns null for "false"', () => {
    const val = ref('false')
    expect(makeValidationError(val, descriptor, false).value).toBeNull()
  })
})

describe('editRequiredMissing guard (mirrors EntityDetailView logic)', () => {
  it('returns true when a required property has an empty value', () => {
    const requiredKeys = new Set(['Priority', 'Maturity'])
    const editProperties = ref([
      { key: 'Priority', value: '' },
      { key: 'Maturity', value: 'Not Assessed' },
    ])
    const missing = computed(() =>
      [...requiredKeys].some((key) => {
        const row = editProperties.value.find((r) => r.key === key)
        return !row || !row.value.trim()
      }),
    )
    expect(missing.value).toBe(true)
  })

  it('returns false when all required properties have values', () => {
    const requiredKeys = new Set(['Priority', 'Maturity'])
    const editProperties = ref([
      { key: 'Priority', value: 'Must' },
      { key: 'Maturity', value: 'Not Assessed' },
    ])
    const missing = computed(() =>
      [...requiredKeys].some((key) => {
        const row = editProperties.value.find((r) => r.key === key)
        return !row || !row.value.trim()
      }),
    )
    expect(missing.value).toBe(false)
  })

  it('returns false when there are no required properties', () => {
    const requiredKeys = new Set<string>()
    const editProperties = ref<{ key: string; value: string }[]>([])
    const missing = computed(() =>
      [...requiredKeys].some((key) => {
        const row = editProperties.value.find((r) => r.key === key)
        return !row || !row.value.trim()
      }),
    )
    expect(missing.value).toBe(false)
  })
})

describe('default pre-population (mirrors EntityCreateView watch logic)', () => {
  it('pre-populates properties with descriptor defaults', () => {
    const descriptors: Record<string, EntityAttributeDescriptor> = {
      Maturity: { type: 'string', enum: ['Not Assessed', 'Initial'], default: 'Not Assessed' },
      Priority: { type: 'string', enum: ['Must', 'Should', 'Could'] },
    }
    const schemaProperties = ['Maturity', 'Priority']
    const populated = schemaProperties.map((key) => ({
      key,
      value: descriptors[key]?.default ?? '',
    }))
    expect(populated[0].value).toBe('Not Assessed')
    expect(populated[1].value).toBe('')
  })
})

describe('TypedPropertyInput — D2 default attribute shapes', () => {
  it('validates a business-object Sensitivity enum against its members', () => {
    const d: EntityAttributeDescriptor = {
      type: 'string',
      enum: ['Public', 'Internal', 'Confidential', 'Strictly Confidential'],
    }
    expect(makeValidationError(ref('Confidential'), d, false).value).toBeNull()
    expect(makeValidationError(ref('Secret'), d, false).value).toContain('Must be one of')
  })

  it('treats a uri-format string (Source Repository) as informative — any value accepted', () => {
    const d: EntityAttributeDescriptor = { type: 'string' }
    expect(makeValidationError(ref('not-a-url'), d, false).value).toBeNull()
    expect(makeValidationError(ref('https://example.com/repo.git'), d, false).value).toBeNull()
  })

  it('applies no scalar validation to an array attribute (Contained Information → list editor)', () => {
    const d: EntityAttributeDescriptor = { type: 'array' }
    expect(makeValidationError(ref('["sbom", "advisories"]'), d, false).value).toBeNull()
  })
})

describe('TypedPropertyInput — declared constraints and formats', () => {
  // These are what the copied mirror could not see: served on the descriptor, bound to the
  // control, and reported by nothing, because the browser's validity state never reaches the
  // form's own error line.
  const withConstraints = (
    constraints: EntityAttributeDescriptor['constraints'],
  ): EntityAttributeDescriptor => ({ type: 'string', constraints })

  it('reports a value shorter than the declared minimum', () => {
    const value = ref('ab')
    expect(makeValidationError(value, withConstraints({ minLength: 3 }), false).value)
      .toBe('Must be at least 3 characters')
  })

  it('reports a value longer than the declared maximum', () => {
    const value = ref('abcd')
    expect(makeValidationError(value, withConstraints({ maxLength: 3 }), false).value)
      .toBe('Must be at most 3 characters')
  })

  it('reports a value the declared pattern rejects', () => {
    const value = ref('nope')
    expect(makeValidationError(value, withConstraints({ pattern: '^[0-9]+$' }), false).value)
      .toBe('Must match ^[0-9]+$')
  })

  it('judges nothing when the declared pattern cannot be parsed', () => {
    const value = ref('anything')
    expect(makeValidationError(value, withConstraints({ pattern: '([' }), false).value).toBeNull()
  })

  it('reports a value that does not satisfy its declared format', () => {
    const value = ref('see the wiki, somewhere')
    const descriptor: EntityAttributeDescriptor = { type: 'string', format: 'uri' }
    expect(makeValidationError(value, descriptor, false).value)
      .toBe('Must be a link or a path, with no spaces')
  })
})
