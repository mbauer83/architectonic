import { describe, it, expect } from 'vitest'
import { entityTypesForDomain, splitVisibleEntityTypes, WIZARD_DRAFT_KEYWORD } from '../WizardDomainStage.helpers'
import type { AuthoringGuidance, EntityTypeGuidance } from '../../../domain'

describe('WIZARD_DRAFT_KEYWORD', () => {
  it('is a stable, non-empty tag', () => {
    expect(WIZARD_DRAFT_KEYWORD).toBe('wizard-draft')
  })
})

const typeGuidance = (name: string, domain?: string): EntityTypeGuidance => ({
  name, prefix: name.slice(0, 3).toUpperCase(), domain, classes: [],
  create_when: '', never_create_when: '',
  permitted_connections: { outgoing: {}, incoming: {}, symmetric: {} },
})

describe('entityTypesForDomain', () => {
  const guidance: AuthoringGuidance = {
    entity_types: [typeGuidance('goal', 'motivation'), typeGuidance('business-process', 'business')],
  }

  it('filters entity types to the requested domain', () => {
    expect(entityTypesForDomain(guidance, 'motivation').map((e) => e.name)).toEqual(['goal'])
  })

  it('returns an empty array for a domain with no matches', () => {
    expect(entityTypesForDomain(guidance, 'technology')).toEqual([])
  })

  it('returns an empty array when guidance is null', () => {
    expect(entityTypesForDomain(null, 'motivation')).toEqual([])
  })

  it('keeps every entry when domain is omitted (GET /api/authoring-guidance?domain=... response shape)', () => {
    // Reproduces the wizard's real call pattern: the backend omits the per-item `domain` field
    // when the whole response is already domain-scoped by the request's own `domain=` param
    // (`_entity_type_guidance`'s `include_domain=False` branch) — filtering on a field that's
    // never present would silently return zero types for every domain.
    const domainScoped: AuthoringGuidance = { entity_types: [typeGuidance('goal'), typeGuidance('driver')] }
    expect(entityTypesForDomain(domainScoped, 'motivation').map((e) => e.name)).toEqual(['goal', 'driver'])
  })
})

describe('splitVisibleEntityTypes', () => {
  it('never shows more than maxVisible types initially', () => {
    const types = ['a', 'b', 'c', 'd', 'e', 'f'].map((n) => typeGuidance(n, 'motivation'))
    const { visible, rest } = splitVisibleEntityTypes(types, 4)
    expect(visible).toHaveLength(4)
    expect(rest).toHaveLength(2)
  })

  it('puts everything in visible when there are fewer than maxVisible types', () => {
    const types = ['a', 'b'].map((n) => typeGuidance(n, 'motivation'))
    const { visible, rest } = splitVisibleEntityTypes(types, 4)
    expect(visible).toHaveLength(2)
    expect(rest).toHaveLength(0)
  })

  it('defaults maxVisible to 4', () => {
    const types = ['a', 'b', 'c', 'd', 'e'].map((n) => typeGuidance(n, 'motivation'))
    expect(splitVisibleEntityTypes(types).visible).toHaveLength(4)
  })

  it('floats priority types (questionnaire spine steps) to the front of the visible slice', () => {
    // Mirrors the common domain, where the alphabetical API order puts junctions before the
    // role/process/service core a beginner should actually see first.
    const types = ['and-junction', 'event', 'function', 'process', 'role', 'service']
      .map((n) => typeGuidance(n, 'common'))
    const { visible, rest } = splitVisibleEntityTypes(types, 4, ['role', 'process', 'service'])
    expect(visible.map((t) => t.name)).toEqual(['role', 'process', 'service', 'and-junction'])
    expect(rest.map((t) => t.name)).toEqual(['event', 'function'])
  })

  it('keeps the original order for types outside the priority list (stable sort)', () => {
    const types = ['a', 'b', 'c', 'd'].map((n) => typeGuidance(n, 'motivation'))
    const { visible } = splitVisibleEntityTypes(types, 4, ['c'])
    expect(visible.map((t) => t.name)).toEqual(['c', 'a', 'b', 'd'])
  })
})
