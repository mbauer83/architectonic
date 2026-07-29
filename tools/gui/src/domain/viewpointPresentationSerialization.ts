/**
 * Presentation builder <-> Appendix-A mapping conversion — the exact counterpart of
 * `src/domain/viewpoints/viewpoint_presentation_serialization.py` / `viewpoint_presentation_parsing.py`.
 */

import { type GroupNode, nextNodeId } from './viewpointCriteria'
import { groupFromMapping, groupToMapping } from './viewpointCriteriaSerialization'
import {
  type ColumnSpecNode,
  type PresentationNode,
  type RangeBandNode,
  type Representation,
  type StyleMode,
  type StyleRuleNode,
  isEdgeCapability,
  mkColumn,
  mkPresentation,
  mkRangeBand,
} from './viewpointPresentation'

const asRecord = (raw: unknown): Record<string, unknown> => raw as Record<string, unknown>
/** See `viewpointDefinitionSerialization.ts`'s `stringOr` for why this exists: `String()`
 * on an `unknown` mapping value trips `@typescript-eslint/no-base-to-string`. */
const stringOr = (v: unknown, fallback: string | null): string | null =>
  typeof v === 'string' || typeof v === 'number' ? String(v) : fallback

// ── to mapping ────────────────────────────────────────────────────────────────

const columnToMapping = (column: ColumnSpecNode): Record<string, unknown> => ({
  label: column.label, source: column.source,
})

const rangeBandToMapping = (band: RangeBandNode): Record<string, unknown> => ({
  minimum: band.minimum, maximum: band.maximum, value: band.value,
})

const styleRuleToMapping = (rule: StyleRuleNode): Record<string, unknown> => {
  const result: Record<string, unknown> = { capability: rule.capability }
  if (rule.appliesTo.length > 0) result.applies_to = [...rule.appliesTo].sort()
  if (rule.mode !== 'match') result.mode = rule.mode
  if (rule.mode === 'match') {
    if (rule.matchCriteria !== null) result.match_criteria = groupToMapping(rule.matchCriteria)
    if (rule.value !== null) result.value = rule.value
  } else if (rule.mode === 'range') {
    if (rule.rangeAttribute !== null) result.range_attribute = rule.rangeAttribute
    if (rule.rangeBands.length > 0) result.range_bands = rule.rangeBands.map(rangeBandToMapping)
  } else {
    if (rule.scaleAttribute !== null) result.scale_attribute = rule.scaleAttribute
    if (rule.scaleMin !== null) result.scale_min = rule.scaleMin
    if (rule.scaleMax !== null) result.scale_max = rule.scaleMax
    if (rule.scaleTokens !== null) result.scale_tokens = [...rule.scaleTokens]
  }
  if (rule.sourceCriteria !== null) result.source_criteria = groupToMapping(rule.sourceCriteria)
  if (rule.targetCriteria !== null) result.target_criteria = groupToMapping(rule.targetCriteria)
  if (rule.disabled) result.disabled = true
  return result
}

export const presentationToMapping = (presentation: PresentationNode): Record<string, unknown> => {
  const result: Record<string, unknown> = { representation: presentation.representation }
  if (Object.keys(presentation.displayOptions).length > 0) result.display_options = presentation.displayOptions
  if (presentation.columns !== null) result.columns = presentation.columns.map(columnToMapping)
  if (presentation.rowBy !== null) result.row_by = presentation.rowBy
  if (presentation.columnBy !== null) result.column_by = presentation.columnBy
  if (presentation.rowCriteria !== null) result.row_criteria = groupToMapping(presentation.rowCriteria)
  if (presentation.columnCriteria !== null) result.column_criteria = groupToMapping(presentation.columnCriteria)
  if (presentation.groupBy !== null) result.group_by = presentation.groupBy
  if (presentation.stylingRules.length > 0) result.styling_rules = presentation.stylingRules.map(styleRuleToMapping)
  if (Object.keys(presentation.defaultStyle).length > 0) result.default_style = presentation.defaultStyle
  if (presentation.targetTypes !== null) result.target_types = presentation.targetTypes
  if (presentation.legibilityBudget !== null) result.legibility_budget = presentation.legibilityBudget
  if (presentation.aggregateBy !== null) result.aggregate_by = presentation.aggregateBy
  return result
}

// ── from mapping ──────────────────────────────────────────────────────────────

const columnFromMapping = (raw: Record<string, unknown>): ColumnSpecNode => {
  const column = mkColumn()
  column.label = String(raw.label)
  column.source = String(raw.source)
  return column
}

const rangeBandFromMapping = (raw: Record<string, unknown>): RangeBandNode => {
  const band = mkRangeBand()
  band.minimum = raw.minimum != null ? Number(raw.minimum) : null
  band.maximum = raw.maximum != null ? Number(raw.maximum) : null
  band.value = String(raw.value)
  return band
}

const matchCriteriaGroup = (raw: unknown, capability: string): GroupNode | null => {
  if (raw == null) return null
  return groupFromMapping(asRecord(raw), isEdgeCapability(capability) ? 'connection' : 'entity')
}

const numberOr = (v: unknown, fallback: number | null): number | null => typeof v === 'number' ? v : fallback

const scaleTokensFromMapping = (raw: unknown): readonly [string, string] | null => {
  if (!Array.isArray(raw) || raw.length !== 2) return null
  return [String(raw[0]), String(raw[1])]
}

const styleRuleFromMapping = (raw: Record<string, unknown>): StyleRuleNode => {
  const capability = String(raw.capability)
  const mode = (raw.mode as StyleMode) ?? 'match'
  const appliesTo = Array.isArray(raw.applies_to) ? raw.applies_to.map(String) : []
  const base = {
    id: nextNodeId(), capability, appliesTo, mode,
    matchCriteria: null, value: null,
    rangeAttribute: null, rangeBands: [],
    scaleAttribute: null, scaleMin: null, scaleMax: null, scaleTokens: null,
    sourceCriteria: raw.source_criteria != null ? groupFromMapping(asRecord(raw.source_criteria), 'entity') : null,
    targetCriteria: raw.target_criteria != null ? groupFromMapping(asRecord(raw.target_criteria), 'entity') : null,
    disabled: raw.disabled === true,
  }
  if (mode === 'match') {
    return { ...base, matchCriteria: matchCriteriaGroup(raw.match_criteria, capability), value: stringOr(raw.value, null) }
  }
  if (mode === 'range') {
    return {
      ...base,
      rangeAttribute: stringOr(raw.range_attribute, null),
      rangeBands: Array.isArray(raw.range_bands) ? raw.range_bands.map((b) => rangeBandFromMapping(asRecord(b))) : [],
    }
  }
  return {
    ...base,
    scaleAttribute: stringOr(raw.scale_attribute, null),
    scaleMin: typeof raw.scale_min === 'string' ? raw.scale_min : numberOr(raw.scale_min, null),
    scaleMax: typeof raw.scale_max === 'string' ? raw.scale_max : numberOr(raw.scale_max, null),
    scaleTokens: scaleTokensFromMapping(raw.scale_tokens),
  }
}

export const presentationFromMapping = (raw: unknown): PresentationNode | null => {
  if (raw == null) return null
  const rec = asRecord(raw)
  const representation = rec.representation as Representation
  const presentation = mkPresentation(representation)
  presentation.displayOptions = typeof rec.display_options === 'object' && rec.display_options != null
    ? asRecord(rec.display_options) : {}
  presentation.columns = Array.isArray(rec.columns) ? rec.columns.map((c) => columnFromMapping(asRecord(c))) : null
  presentation.rowBy = stringOr(rec.row_by, null)
  presentation.columnBy = stringOr(rec.column_by, null)
  presentation.rowCriteria = rec.row_criteria != null ? groupFromMapping(asRecord(rec.row_criteria), 'entity') : null
  presentation.columnCriteria = rec.column_criteria != null
    ? groupFromMapping(asRecord(rec.column_criteria), 'entity') : null
  presentation.groupBy = stringOr(rec.group_by, null)
  presentation.stylingRules = Array.isArray(rec.styling_rules)
    ? rec.styling_rules.map((r) => styleRuleFromMapping(asRecord(r))) : []
  presentation.defaultStyle = typeof rec.default_style === 'object' && rec.default_style != null
    ? Object.fromEntries(Object.entries(asRecord(rec.default_style)).map(([k, v]) => [k, String(v)])) : {}
  presentation.legibilityBudget = typeof rec.legibility_budget === 'number' ? rec.legibility_budget : null
  presentation.aggregateBy = typeof rec.aggregate_by === 'string' ? rec.aggregate_by : null
  presentation.targetTypes = Array.isArray(rec.target_types)
    ? rec.target_types.map((t) => String(t)) : null
  return presentation
}
