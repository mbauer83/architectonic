/**
 * Presentation builder model: representation, style rules (match/range), columns, and
 * matrix axes — mirrors `PresentationSpec`/`StyleRule`/`RangeBand`/`ColumnSpec` in
 * `src/domain/viewpoints/viewpoints.py`. See `viewpointCriteria.ts` for the criteria-tree types
 * style-rule `mode="match"` criteria and matrix criteria-axes reuse unmodified.
 */

import { type GroupNode, mkGroup, nextNodeId } from './viewpointCriteria'

export type Representation = 'exploration' | 'table' | 'matrix' | 'diagram'
export type StyleMode = 'match' | 'range' | 'scale'

export const REPRESENTATION_CAPABILITIES: Readonly<Record<Representation, readonly string[]>> = {
  exploration: ['node_shape', 'node_icon', 'node_color', 'edge_color', 'edge_emphasis', 'cluster_grouping'],
  table: ['columns', 'badges', 'sort', 'row_grouping'],
  matrix: ['row_by', 'column_by', 'cell_emphasis'],
  diagram: ['node_color', 'edge_color', 'edge_emphasis', 'cluster_grouping'],
}

/** GUI-only convention — the domain treats `StyleRule.value` as a freeform opaque string
 * (a surface adapter resolves it to a shape/icon/color per capability); this is the fixed
 * token vocabulary the signed-off wireframe standardized the picker on. */
export const STYLE_TOKENS: readonly string[] = ['emphasis', 'positive', 'caution', 'critical', 'neutral']

export const GROUP_BY_DIMENSIONS: readonly string[] = ['type', 'specialization', 'group']

export interface RangeBandNode {
  readonly id: string
  minimum: number | null
  maximum: number | null
  value: string
}

export const mkRangeBand = (): RangeBandNode => ({ id: nextNodeId(), minimum: null, maximum: null, value: STYLE_TOKENS[0] })

export interface StyleRuleNode {
  readonly id: string
  capability: string
  appliesTo: string[]
  mode: StyleMode
  matchCriteria: GroupNode | null
  rangeAttribute: string | null
  rangeBands: RangeBandNode[]
  value: string | null
  /** `mode === 'scale'`: the numeric/date attribute path driving a continuous
   * interpolation, its bounds (`null` = data-driven), and its two gradient-endpoint
   * tokens — an author-chosen opaque pair, not restricted to `STYLE_TOKENS`. */
  scaleAttribute: string | null
  scaleMin: number | string | null
  scaleMax: number | string | null
  scaleTokens: readonly [string, string] | null
  /** Edge rules only: entity criteria the connection's source/target endpoint must
   * satisfy — how a boundary view accents exactly the edges crossing a group boundary. */
  sourceCriteria: GroupNode | null
  targetCriteria: GroupNode | null
  /** Quarantined: saveable exactly as inherited but never evaluated (fork-safe escape
   * hatch for inherited rules whose attribute no longer resolves). */
  disabled: boolean
}

/** An `edge_*` capability's `match_criteria` is connection criteria; every other
 * capability (including matrix's `cell_emphasis`) takes entity criteria. */
export const isEdgeCapability = (capability: string): boolean => capability.startsWith('edge_')

export const mkStyleRule = (representation: Representation): StyleRuleNode => {
  const capability = REPRESENTATION_CAPABILITIES[representation][0]
  return {
    id: nextNodeId(), capability, appliesTo: [], mode: 'match',
    matchCriteria: mkGroup(isEdgeCapability(capability) ? 'connection' : 'entity'),
    rangeAttribute: null, rangeBands: [], value: STYLE_TOKENS[0],
    scaleAttribute: null, scaleMin: null, scaleMax: null, scaleTokens: null,
    sourceCriteria: null, targetCriteria: null, disabled: false,
  }
}

/** The gradient-endpoint pair a fresh scale rule starts from — the distance heat pair,
 * matching the most common scale use (styling by hop distance from an anchor). */
export const DEFAULT_SCALE_TOKENS: readonly [string, string] = ['heat-near', 'heat-far']

/** Switching a rule's mode clears every other mode's fields (a definition mixing fields
 * across modes is rejected server-side) and seeds the target mode's required ones:
 * `match` gets a fresh criteria group + first token, `scale` gets the default endpoint
 * pair. Same-mode switches are identity. */
export const withStyleMode = (rule: StyleRuleNode, mode: StyleMode): StyleRuleNode => {
  if (rule.mode === mode) return rule
  const cleared: StyleRuleNode = {
    ...rule, mode, matchCriteria: null, value: null, rangeAttribute: null, rangeBands: [],
    scaleAttribute: null, scaleMin: null, scaleMax: null, scaleTokens: null,
  }
  if (mode === 'match') {
    return {
      ...cleared,
      matchCriteria: mkGroup(isEdgeCapability(rule.capability) ? 'connection' : 'entity'),
      value: STYLE_TOKENS[0],
    }
  }
  return mode === 'scale' ? { ...cleared, scaleTokens: DEFAULT_SCALE_TOKENS } : cleared
}

/** A scale bound as typed: empty = data-driven (`null`), numeric text = number, anything
 * else (e.g. an ISO date) stays a string — the same shapes the backend bound parser takes. */
export const parseScaleBound = (raw: string): number | string | null => {
  const trimmed = raw.trim()
  if (trimmed === '') return null
  const parsed = Number(trimmed)
  return Number.isNaN(parsed) ? trimmed : parsed
}

export type ExplorationLayout = 'clusters' | 'radial' | 'force'

export const EXPLORATION_LAYOUTS: readonly ExplorationLayout[] = ['clusters', 'radial', 'force']

/** The exploration `display_options.layout` value, if present and recognised. */
export const layoutOption = (displayOptions: Record<string, unknown>): ExplorationLayout | null => {
  const value = displayOptions.layout
  return typeof value === 'string' && (EXPLORATION_LAYOUTS as readonly string[]).includes(value)
    ? (value as ExplorationLayout)
    : null
}

/** Display options with `layout` set, or with the key removed entirely (`null` = auto —
 * absence is the wire representation of the default). */
export const withLayoutOption = (
  displayOptions: Record<string, unknown>,
  layout: ExplorationLayout | null,
): Record<string, unknown> => {
  const next = { ...displayOptions }
  if (layout === null) delete next.layout
  else next.layout = layout
  return next
}

export interface ColumnSpecNode {
  readonly id: string
  label: string
  source: string
}

export const mkColumn = (): ColumnSpecNode => ({ id: nextNodeId(), label: '', source: 'name' })

export type MatrixAxisMode = 'grouped' | 'criteria'

export interface PresentationNode {
  representation: Representation
  displayOptions: Record<string, unknown>
  columns: ColumnSpecNode[] | null
  rowBy: string | null
  columnBy: string | null
  rowCriteria: GroupNode | null
  columnCriteria: GroupNode | null
  groupBy: string | null
  stylingRules: StyleRuleNode[]
  defaultStyle: Record<string, string>
  /** The TARGET population this view is about — drives honest-empty messaging. Null =
   * undeclared (in query mode that means absence claims are suppressed at execution). */
  targetTypes: string[] | null
  /** Node count above which the result opens aggregated on graph surfaces (null =
   * deployment default). */
  legibilityBudget: number | null
  /** Aggregation dimension for over-budget results ('group' | 'domain' | 'type'). */
  aggregateBy: string | null
}

export const mkPresentation = (representation: Representation): PresentationNode => ({
  representation, displayOptions: {}, columns: representation === 'table' ? [] : null,
  rowBy: null, columnBy: null, rowCriteria: null, columnCriteria: null, groupBy: null,
  stylingRules: [], defaultStyle: {}, targetTypes: null, legibilityBudget: null, aggregateBy: null,
})

export const matrixAxisMode = (presentation: PresentationNode): MatrixAxisMode | null => {
  if (presentation.rowBy !== null || presentation.columnBy !== null) return 'grouped'
  if (presentation.rowCriteria !== null || presentation.columnCriteria !== null) return 'criteria'
  return null
}
