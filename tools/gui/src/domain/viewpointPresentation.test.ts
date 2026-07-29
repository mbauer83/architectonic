import { describe, expect, it } from 'vitest'
import {
  DEFAULT_SCALE_TOKENS,
  EXPLORATION_LAYOUTS,
  layoutOption,
  mkPresentation,
  mkStyleRule,
  parseScaleBound,
  withLayoutOption,
  withStyleMode,
} from './viewpointPresentation'
import type { StyleRuleNode } from './viewpointPresentation'
import { presentationFromMapping, presentationToMapping } from './viewpointPresentationSerialization'
import { mkGroup } from './viewpointCriteria'

const scaleRule = (): StyleRuleNode => ({
  ...mkStyleRule('exploration'),
  mode: 'scale', matchCriteria: null, value: null,
  scaleAttribute: 'derived.impact-distance', scaleMin: 0, scaleMax: 6,
  scaleTokens: ['heat-low', '#123456'],
})

describe('withStyleMode', () => {
  it('is identity when the mode is unchanged', () => {
    const rule = mkStyleRule('exploration')
    expect(withStyleMode(rule, 'match')).toBe(rule)
  })

  it('clears match fields and seeds default endpoints when switching to scale', () => {
    const rule = mkStyleRule('exploration')
    const switched = withStyleMode(rule, 'scale')
    expect(switched.matchCriteria).toBeNull()
    expect(switched.value).toBeNull()
    expect(switched.scaleTokens).toEqual(DEFAULT_SCALE_TOKENS)
    expect(switched.scaleAttribute).toBeNull()
  })

  it('clears every scale field when switching to range', () => {
    const switched = withStyleMode(scaleRule(), 'range')
    expect(switched.mode).toBe('range')
    expect(switched.scaleAttribute).toBeNull()
    expect(switched.scaleMin).toBeNull()
    expect(switched.scaleMax).toBeNull()
    expect(switched.scaleTokens).toBeNull()
    expect(switched.rangeBands).toEqual([])
  })

  it('seeds a fresh criteria group and first token when switching back to match', () => {
    const switched = withStyleMode(scaleRule(), 'match')
    expect(switched.matchCriteria?.groupKind).toBe('entity')
    expect(switched.value).toBe('emphasis')
    expect(switched.scaleTokens).toBeNull()
  })

  it('gives an edge capability a connection criteria group', () => {
    const rule = { ...scaleRule(), capability: 'edge_color' }
    expect(withStyleMode(rule, 'match').matchCriteria?.groupKind).toBe('connection')
  })
})

describe('parseScaleBound', () => {
  it('maps empty input to null (data-driven bound)', () => {
    expect(parseScaleBound('')).toBeNull()
    expect(parseScaleBound('   ')).toBeNull()
  })

  it('parses numeric text to a number', () => {
    expect(parseScaleBound('42')).toBe(42)
    expect(parseScaleBound(' -1.5 ')).toBe(-1.5)
  })

  it('keeps non-numeric text (e.g. an ISO date) as a string', () => {
    expect(parseScaleBound('2026-01-01')).toBe('2026-01-01')
  })
})

describe('layout display option', () => {
  it('reads a recognised layout and rejects unknown values', () => {
    expect(layoutOption({ layout: 'radial' })).toBe('radial')
    expect(layoutOption({ layout: 'spiral' })).toBeNull()
    expect(layoutOption({})).toBeNull()
  })

  it('sets a layout without disturbing other display options', () => {
    expect(withLayoutOption({ label_attribute: 'name' }, 'clusters'))
      .toEqual({ label_attribute: 'name', layout: 'clusters' })
  })

  it('removes the key entirely for auto (null)', () => {
    expect(withLayoutOption({ layout: 'force', label_attribute: 'name' }, null))
      .toEqual({ label_attribute: 'name' })
  })

  it('covers exactly the backend-validated layouts', () => {
    expect(EXPLORATION_LAYOUTS).toEqual(['clusters', 'radial', 'force'])
  })
})

describe('endpoint criteria and quarantined rules round-trip', () => {
  it('serializes source/target criteria and disabled, and reads them back', () => {
    const presentation = mkPresentation('exploration')
    const rule = mkStyleRule('exploration')
    rule.capability = 'edge_color'
    rule.matchCriteria = mkGroup('connection')
    rule.sourceCriteria = mkGroup('entity')
    rule.targetCriteria = mkGroup('entity')
    rule.disabled = true
    presentation.stylingRules = [rule]
    const mapping = presentationToMapping(presentation)
    const serialized = (mapping.styling_rules as Record<string, unknown>[])[0]
    expect(serialized.disabled).toBe(true)
    expect(serialized.source_criteria).toBeDefined()
    expect(serialized.target_criteria).toBeDefined()
    const parsed = presentationFromMapping(mapping)!
    expect(parsed.stylingRules[0].disabled).toBe(true)
    expect(parsed.stylingRules[0].sourceCriteria).not.toBeNull()
    expect(parsed.stylingRules[0].targetCriteria).not.toBeNull()
  })

  it('omits the endpoint keys and disabled=false for plain rules', () => {
    const presentation = mkPresentation('exploration')
    presentation.stylingRules = [mkStyleRule('exploration')]
    const serialized = (presentationToMapping(presentation).styling_rules as Record<string, unknown>[])[0]
    expect('source_criteria' in serialized).toBe(false)
    expect('target_criteria' in serialized).toBe(false)
    expect('disabled' in serialized).toBe(false)
  })
})
