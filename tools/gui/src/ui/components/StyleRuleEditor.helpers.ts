/**
 * Pure helpers for `StyleRuleEditor.vue`: capability options per representation, numeric
 * attribute choices for range mode, and the derived legend — a read-only summary of every
 * opaque style token actually in use, never a separately authored thing.
 */

import type { CriteriaCatalog } from '../../domain'
import type { PresentationNode, Representation } from '../../domain/viewpointPresentation'
import { REPRESENTATION_CAPABILITIES } from '../../domain/viewpointPresentation'
import { attributeOptions } from './CriteriaTreeBuilder.helpers'

export const capabilitiesFor = (representation: Representation): readonly string[] =>
  REPRESENTATION_CAPABILITIES[representation]

const NUMERIC_TYPES = new Set(['integer', 'number', 'date'])

/** Attribute paths eligible as a range rule's `range_attribute` — numeric/date schema
 * attributes only (reserved paths carry no declared type and so are never numeric here). */
export const numericAttributeOptions = (catalog: CriteriaCatalog): string[] =>
  attributeOptions('entity', catalog)
    .filter((a) => a.declaredType !== null && NUMERIC_TYPES.has(a.declaredType))
    .map((a) => a.path)

export interface LegendEntry {
  token: string
  usageCount: number
}

/** Every distinct token a presentation's style rules/default style actually reference,
 * sorted by first-seen order — the "legend" is read off the definition, never a separate
 * thing an author maintains by hand. */
export const derivedLegend = (presentation: PresentationNode): LegendEntry[] => {
  const counts = new Map<string, number>()
  const bump = (token: string | null) => {
    if (token === null) return
    counts.set(token, (counts.get(token) ?? 0) + 1)
  }
  for (const rule of presentation.stylingRules) {
    if (rule.mode === 'match') bump(rule.value)
    else if (rule.mode === 'range') for (const band of rule.rangeBands) bump(band.value)
    else for (const token of rule.scaleTokens ?? []) bump(token)
  }
  for (const token of Object.values(presentation.defaultStyle)) bump(token)
  return [...counts.entries()].map(([token, usageCount]) => ({ token, usageCount }))
}
