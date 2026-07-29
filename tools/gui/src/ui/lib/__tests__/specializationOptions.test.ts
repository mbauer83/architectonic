import { describe, it, expect } from 'vitest'
import {
  specializationOptionsForEntityType,
  specializationOptionsForConnectionType,
  specializationOptionLabel,
} from '../specializationOptions'
import type { AuthoringGuidance, SpecializationGuidance } from '../../../domain'

const spec = (slug: string, name: string): SpecializationGuidance => ({
  slug, name, description: '', create_when: '', never_create_when: '',
})

const guidance: AuthoringGuidance = {
  entity_types: [
    {
      name: 'collaboration', prefix: 'COL', classes: [], create_when: '', never_create_when: '',
      permitted_connections: { outgoing: {}, incoming: {}, symmetric: {} },
      specializations: [spec('business-collaboration', 'Business Collaboration'), spec('application-collaboration', 'Application Collaboration')],
    },
    {
      name: 'goal', prefix: 'GOA', classes: [], create_when: '', never_create_when: '',
      permitted_connections: { outgoing: {}, incoming: {}, symmetric: {} },
      specializations: [],
    },
  ],
  connection_types: [
    { name: 'archimate-assignment', specializations: [spec('responsibility-assignment', 'Responsibility Assignment')] },
  ],
}

describe('specializationOptionsForEntityType', () => {
  it('returns the declared specializations for a known type', () => {
    expect(specializationOptionsForEntityType(guidance, 'collaboration')).toEqual([
      spec('business-collaboration', 'Business Collaboration'),
      spec('application-collaboration', 'Application Collaboration'),
    ])
  })

  it('returns an empty list for a type with none declared', () => {
    expect(specializationOptionsForEntityType(guidance, 'goal')).toEqual([])
  })

  it('returns an empty list for an unknown type', () => {
    expect(specializationOptionsForEntityType(guidance, 'unknown-type')).toEqual([])
  })

  it('returns an empty list when guidance is null (not yet loaded)', () => {
    expect(specializationOptionsForEntityType(null, 'collaboration')).toEqual([])
  })

  it('returns an empty list when entity_types is absent from the payload', () => {
    expect(specializationOptionsForEntityType({}, 'collaboration')).toEqual([])
  })
})

describe('specializationOptionsForConnectionType', () => {
  it('returns the declared specializations for a known connection type', () => {
    expect(specializationOptionsForConnectionType(guidance, 'archimate-assignment')).toEqual([
      spec('responsibility-assignment', 'Responsibility Assignment'),
    ])
  })

  it('returns an empty list for a connection type absent from the block (none declared)', () => {
    expect(specializationOptionsForConnectionType(guidance, 'archimate-association')).toEqual([])
  })

  it('returns an empty list when guidance is null', () => {
    expect(specializationOptionsForConnectionType(null, 'archimate-assignment')).toEqual([])
  })
})

describe('specializationOptionLabel', () => {
  it('prefers the display name', () => {
    expect(specializationOptionLabel(spec('business-collaboration', 'Business Collaboration'))).toBe(
      'Business Collaboration',
    )
  })

  it('falls back to the slug when name is empty', () => {
    expect(specializationOptionLabel(spec('business-collaboration', ''))).toBe('business-collaboration')
  })
})
