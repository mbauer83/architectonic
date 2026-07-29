import { describe, expect, it } from 'vitest'
import {
  coerceParameterValue, draftFromWireValues, initialParameterDraft, missingRequiredParameters,
  needsParameterPrompt, parameterSignatureOf, parametersToWireValues,
} from './viewpointExecutionParameters'
import type { ViewpointDefinitionEnvelope } from '../../domain'

const envelopeWithParameters = (parameters: unknown[]): ViewpointDefinitionEnvelope => ({
  slug: 'x', version: 1, name: 'X', tier: 'module',
  scope_summary: { unrestricted: true }, query_summary: null, fork_status: null,
  query: { query_schema: 1, entity_criteria: { kind: 'group', conjunction: 'and', children: [] }, parameters },
})

describe('parameterSignatureOf', () => {
  it('is empty for a scope-only definition (no query)', () => {
    const envelope: ViewpointDefinitionEnvelope = {
      slug: 'x', version: 1, name: 'X', tier: 'module', scope_summary: { unrestricted: true }, query_summary: null, fork_status: null,
    }
    expect(parameterSignatureOf(envelope)).toEqual([])
  })

  it('is empty for a query with no declared parameters', () => {
    expect(parameterSignatureOf(envelopeWithParameters([]))).toEqual([])
  })

  it('parses a declared parameter signature', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([{ name: 'anchor', type: 'entity-id' }]))
    expect(signature).toHaveLength(1)
    expect(signature[0]).toMatchObject({ name: 'anchor', valueType: 'entity-id', required: true })
  })
})

describe('needsParameterPrompt', () => {
  it('is false with no parameters', () => {
    expect(needsParameterPrompt([])).toBe(false)
  })

  it('is false when every required parameter has a default', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([{ name: 'limit', type: 'integer', default: 10 }]))
    expect(needsParameterPrompt(signature)).toBe(false)
  })

  it('is false for an optional parameter with no default', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([{ name: 'note', type: 'string', required: false }]))
    expect(needsParameterPrompt(signature)).toBe(false)
  })

  it('is true when a required parameter has no default', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([{ name: 'anchor', type: 'entity-id' }]))
    expect(needsParameterPrompt(signature)).toBe(true)
  })
})

describe('initialParameterDraft / missingRequiredParameters', () => {
  it('seeds the draft from each parameter default, empty for undefaulted', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([
      { name: 'limit', type: 'integer', default: 10 },
      { name: 'anchor', type: 'entity-id' },
    ]))
    expect(initialParameterDraft(signature)).toEqual({ limit: '10', anchor: '' })
  })

  it('flags only required parameters with a blank draft value', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([
      { name: 'anchor', type: 'entity-id' },
      { name: 'note', type: 'string', required: false },
    ]))
    const missing = missingRequiredParameters(signature, { anchor: '', note: '' })
    expect(missing.map((p) => p.name)).toEqual(['anchor'])
  })

  it('is empty once every required field has a non-blank value', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([{ name: 'anchor', type: 'entity-id' }]))
    expect(missingRequiredParameters(signature, { anchor: 'ARC@1' })).toEqual([])
  })
})

describe('coerceParameterValue', () => {
  it('parses integer and number types', () => {
    expect(coerceParameterValue('integer', '5')).toBe(5)
    expect(coerceParameterValue('number', '2.5')).toBe(2.5)
  })

  it('yields null for unparseable numeric input rather than silently coercing to 0', () => {
    expect(coerceParameterValue('integer', 'not-a-number')).toBeNull()
  })

  it('parses boolean from its checkbox string', () => {
    expect(coerceParameterValue('boolean', 'true')).toBe(true)
    expect(coerceParameterValue('boolean', 'false')).toBe(false)
  })

  it('passes string/slug/entity-id/date through unchanged', () => {
    expect(coerceParameterValue('string', 'hello')).toBe('hello')
    expect(coerceParameterValue('slug', 'my-slug')).toBe('my-slug')
    expect(coerceParameterValue('entity-id', 'ARC@1000000001')).toBe('ARC@1000000001')
    expect(coerceParameterValue('date', '2026-01-01')).toBe('2026-01-01')
  })
})

describe('parametersToWireValues', () => {
  it('omits a blank optional parameter entirely (unsupplied, not empty-string)', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([
      { name: 'anchor', type: 'entity-id' },
      { name: 'note', type: 'string', required: false },
    ]))
    expect(parametersToWireValues(signature, { anchor: 'ARC@1', note: '' })).toEqual({ anchor: 'ARC@1' })
  })

  it('coerces every supplied value to its declared type', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([
      { name: 'limit', type: 'integer' },
      { name: 'flag', type: 'boolean' },
    ]))
    expect(parametersToWireValues(signature, { limit: '7', flag: 'true' })).toEqual({ limit: 7, flag: true })
  })
})

describe('set-valued (cardinality: many) parameters', () => {
  const scopeSig = () => parameterSignatureOf(envelopeWithParameters([{
    name: 'scope', type: 'string', cardinality: 'many',
    allowed_values: ['goal', 'outcome', 'requirement'], min_items: 1,
    required: false, default: ['goal', 'outcome', 'requirement'],
  }]))

  it('parses cardinality, allowed_values, min_items and an array default', () => {
    const [p] = scopeSig()
    expect(p).toMatchObject({ cardinality: 'many', allowedValues: ['goal', 'outcome', 'requirement'], minItems: 1 })
    expect(p.default).toEqual(['goal', 'outcome', 'requirement'])
  })

  it('seeds the draft with a COPY of the default array (never aliases the declaration)', () => {
    const [p] = scopeSig()
    const draft = initialParameterDraft([p])
    expect(draft.scope).toEqual(['goal', 'outcome', 'requirement'])
    expect(draft.scope).not.toBe(p.default)
  })

  it('sends the member array verbatim on the wire', () => {
    expect(parametersToWireValues(scopeSig(), { scope: ['requirement', 'goal'] })).toEqual({
      scope: ['requirement', 'goal'],
    })
  })

  it('omits an empty set (unsupplied optional), never sends []', () => {
    expect(parametersToWireValues(scopeSig(), { scope: [] })).toEqual({})
  })

  it('an empty required set is still missing', () => {
    const required = parameterSignatureOf(envelopeWithParameters([{
      name: 'scope', type: 'string', cardinality: 'many', allowed_values: ['a', 'b'], min_items: 1,
    }]))
    expect(missingRequiredParameters(required, { scope: [] }).map((p) => p.name)).toEqual(['scope'])
    expect(missingRequiredParameters(required, { scope: ['a'] })).toEqual([])
  })

  it('an open set (no allowed_values) parses with an empty vocabulary', () => {
    const [group] = parameterSignatureOf(envelopeWithParameters([{
      name: 'group', type: 'slug', cardinality: 'many', min_items: 1, required: false,
    }]))
    expect(group.cardinality).toBe('many')
    expect(group.allowedValues).toEqual([])
  })

  it('seeds a draft from the bound wire values (the toolbar reflects the current result)', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([
      { name: 'scope', type: 'string', cardinality: 'many', allowed_values: ['goal', 'outcome'], min_items: 1,
        required: false, default: ['goal', 'outcome'] },
      { name: 'gaps_only', type: 'boolean', required: false, default: false },
    ]))
    const draft = draftFromWireValues(signature, { scope: ['goal'], gaps_only: true })
    expect(draft).toEqual({ scope: ['goal'], gaps_only: 'true' })
  })

  it('falls back to each default for wire values the caller did not supply', () => {
    const signature = parameterSignatureOf(envelopeWithParameters([
      { name: 'scope', type: 'string', cardinality: 'many', allowed_values: ['goal', 'outcome'], min_items: 1,
        required: false, default: ['goal', 'outcome'] },
    ]))
    expect(draftFromWireValues(signature, {})).toEqual({ scope: ['goal', 'outcome'] })
  })
})
