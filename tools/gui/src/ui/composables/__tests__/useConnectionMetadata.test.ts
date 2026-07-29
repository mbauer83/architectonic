import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useConnectionMetadata } from '../useConnectionMetadata'
import type { AuthoringGuidance } from '../../../domain'

/** Minimal guidance carrying one connection type with an optional base schema + specializations. */
const guidanceWith = (
  metadata_schema: unknown,
  specializations: Array<{ slug: string; name: string; metadata_schema: unknown }> = [],
): AuthoringGuidance =>
  ({
    entity_types: [],
    connection_types: [{ name: 'archimate-flow', specializations, metadata_schema }],
  }) as unknown as AuthoringGuidance

const schema = (properties: string[], required: string[] = []) => ({
  properties,
  required,
  descriptors: Object.fromEntries(properties.map((p) => [p, { type: 'string' }])),
})

describe('useConnectionMetadata — profile gate', () => {
  it('hasProfile is false when the type declares no metadata schema', () => {
    const { hasProfile, schemaInfo } = useConnectionMetadata(
      ref(guidanceWith(null)), ref('archimate-flow'), ref(''),
    )
    expect(schemaInfo.value).toBeNull()
    expect(hasProfile.value).toBe(false)
  })

  it('hasProfile is false when the schema declares zero properties (no empty section)', () => {
    const { hasProfile } = useConnectionMetadata(
      ref(guidanceWith(schema([]))), ref('archimate-flow'), ref(''),
    )
    expect(hasProfile.value).toBe(false)
  })

  it('hasProfile is true once the schema declares at least one property', () => {
    const { hasProfile, schemaInfo } = useConnectionMetadata(
      ref(guidanceWith(schema(['weight']))), ref('archimate-flow'), ref(''),
    )
    expect(hasProfile.value).toBe(true)
    expect(schemaInfo.value?.properties).toEqual(['weight'])
  })

  it('reveals a specialization-scoped profile only once that specialization is selected', () => {
    const guidance = ref(
      guidanceWith(null, [{ slug: 'money-flow', name: 'Money', metadata_schema: schema(['amount'], ['amount']) }]),
    )
    const specialization = ref('')
    const { hasProfile } = useConnectionMetadata(guidance, ref('archimate-flow'), specialization)
    expect(hasProfile.value).toBe(false) // base type has no profile — no section on create OR edit
    specialization.value = 'money-flow'
    expect(hasProfile.value).toBe(true) // choosing the specialization reveals it, identically both sides
  })

  it('surfaces quarantine state from the effective schema', () => {
    const quarantined = { ...schema(['x']), quarantined: true, conflicts: ['dup'] }
    const { quarantine } = useConnectionMetadata(
      ref(guidanceWith(quarantined)), ref('archimate-flow'), ref(''),
    )
    expect(quarantine.value.quarantined).toBe(true)
    expect(quarantine.value.conflicts).toEqual(['dup'])
  })

  it('exposes the connection type specialization options', () => {
    const { specializationOptions } = useConnectionMetadata(
      ref(guidanceWith(null, [{ slug: 'money-flow', name: 'Money', metadata_schema: null }])),
      ref('archimate-flow'),
      ref(''),
    )
    expect(specializationOptions.value.map((s) => s.slug)).toEqual(['money-flow'])
  })
})
