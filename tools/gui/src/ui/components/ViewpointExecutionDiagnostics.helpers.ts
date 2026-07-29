/**
 * Pure diagnostics/legend logic for the viewpoint-execution diagnostics panel — shared by
 * every execution representation (exploration, table, matrix, diagram) so "empty",
 * "truncated", and "unsupported capability" states, and the derived legend, are computed
 * identically everywhere.
 */

import { REPRESENTATION_CAPABILITIES, type PresentationNode, type Representation } from '../../domain/viewpointPresentation'
import type { ScaleLegendData, StyleRuleOutcome, ViewpointExecutionResult } from '../../domain'
import { tokenColor } from '../lib/viewpointStyleTokens'

export interface ExecutionDiagnostics {
  readonly isEmpty: boolean
  readonly emptyReason: string | null
  /** True statement about an absent TARGET population ("this model contains no X;
   * showing …") — only ever set when the definition DECLARES its target population and
   * that population is empty while other content renders. Null otherwise: a guessed
   * absence claim is worse than none. */
  readonly absenceStatement: string | null
  readonly truncated: boolean
  readonly truncationMessage: string | null
  readonly totalEntityCount: number
  readonly returnedEntityCount: number
  readonly totalConnectionCount: number
  readonly returnedConnectionCount: number
  readonly unsupportedCapabilities: readonly string[]
  readonly warnings: readonly string[]
}

const plural = (count: number, noun: string): string => `${count} ${noun}${count === 1 ? '' : 's'}`

/** The honest-empty sentence for a declared-but-absent target population. */
export const absenceStatementFor = (result: ViewpointExecutionResult | null): string | null => {
  const population = result?.target_population
  if (!population || population.target_count > 0) return null
  const incidental = Object.entries(population.incidental_type_counts)
  if (incidental.length === 0 && population.structural_count === 0) return null
  const shown = [
    ...incidental.map(([type, count]) => plural(count, type)),
    ...(population.structural_count > 0
      ? [`${population.structural_count} structural element${population.structural_count === 1 ? '' : 's'} (junctions/groupings)`]
      : []),
  ]
  return `This model contains no ${population.target_types.join(' or ')} elements; showing ${shown.join(' and ')}.`
}

const usedCapabilities = (presentation: PresentationNode | null): string[] => {
  if (!presentation) return []
  const fromRules = presentation.stylingRules.map((rule) => rule.capability)
  const fromDefaults = Object.keys(presentation.defaultStyle)
  return [...new Set([...fromRules, ...fromDefaults])]
}

/** Capabilities the definition uses but the *current* representation surface can't
 * render (e.g. an exploration-authored rule viewed as `table`) — surfaced as a warning,
 * never silently dropped. */
export const computeUnsupportedCapabilities = (
  presentation: PresentationNode | null,
  representation: Representation,
): readonly string[] => {
  const supported = new Set(REPRESENTATION_CAPABILITIES[representation])
  return usedCapabilities(presentation).filter((capability) => !supported.has(capability))
}

export const computeExecutionDiagnostics = (
  result: ViewpointExecutionResult | null,
  presentation: PresentationNode | null,
  representation: Representation,
): ExecutionDiagnostics => {
  const totalEntityCount = result?.total_entity_count ?? 0
  const returnedEntityCount = result?.returned_entity_count ?? 0
  const totalConnectionCount = result?.total_connection_count ?? 0
  const returnedConnectionCount = result?.returned_connection_count ?? 0
  // A never-run state (e.g. the parameter dialog was cancelled) is NOT an empty result:
  // "no entities match" would be a statement about a query that never executed.
  const isEmpty = result !== null && totalEntityCount === 0
  const emptyReason = result === null
    ? 'Not executed — this viewpoint has not been run.'
    : isEmpty
      ? "No entities in the current model match this viewpoint's criteria."
      : returnedEntityCount === 0
        ? 'Every matching entity was truncated by the current limit.'
        : null
  const truncated = result?.truncated ?? false
  const truncationMessage = truncated
    ? `Showing ${returnedEntityCount} of ${totalEntityCount} entities (limit ${result?.entity_limit ?? 0}); ` +
      'expanded context members are dropped before primary matches.'
    : null
  return {
    isEmpty,
    emptyReason,
    absenceStatement: absenceStatementFor(result),
    truncated,
    truncationMessage,
    totalEntityCount,
    returnedEntityCount,
    totalConnectionCount,
    returnedConnectionCount,
    unsupportedCapabilities: computeUnsupportedCapabilities(presentation, representation),
    warnings: result?.warnings ?? [],
  }
}

export interface LegendEntry {
  readonly capability: string
  readonly token: string
  readonly label: string
  /** Quiet per-rule outcome badge — '0 matches' for a valid rule that matched nothing
   * this execution (a legitimate state, deliberately NOT a warning). Null when the rule
   * applied or no outcome data is available. */
  readonly note: string | null
}

const outcomeNote = (outcome: StyleRuleOutcome | undefined): string | null => {
  if (outcome === undefined) return null
  if (outcome.kind === 'expected-empty') return '0 matches'
  if (outcome.kind === 'disabled') return 'disabled'
  return null
}

/** Every surface renders its legend mechanically from `styling_rules` + `range_bands` +
 * `default_style` — nothing to author separately. `scale` mode has no discrete bands to
 * enumerate here; its own continuous spectrum is rendered by `deriveScaleGradients`
 * instead, never as fabricated per-band entries. */
export const deriveLegend = (
  presentation: PresentationNode | null,
  ruleOutcomes: readonly StyleRuleOutcome[] = [],
): readonly LegendEntry[] => {
  if (!presentation) return []
  const outcomeByIndex = new Map(ruleOutcomes.map((outcome) => [outcome.rule_index, outcome]))
  const entries: LegendEntry[] = []
  presentation.stylingRules.forEach((rule, index) => {
    const note = outcomeNote(outcomeByIndex.get(index))
    if (rule.mode === 'match') {
      if (rule.value !== null) {
        entries.push({
          capability: rule.capability,
          token: rule.value,
          label: rule.appliesTo.length > 0 ? rule.appliesTo.join(', ') : 'matching criteria',
          note,
        })
      }
    } else if (rule.mode === 'range') {
      for (const band of rule.rangeBands) {
        const lo = band.minimum ?? '-∞'
        const hi = band.maximum ?? '∞'
        entries.push({
          capability: rule.capability,
          token: band.value,
          label: `${rule.rangeAttribute ?? '?'} in [${lo}, ${hi})`,
          note,
        })
      }
    }
  })
  for (const [capability, token] of Object.entries(presentation.defaultStyle)) {
    entries.push({ capability, token, label: 'default', note: null })
  }
  return entries
}

export interface ScaleGradientLegend {
  readonly capability: string
  readonly gradientCss: string
  readonly minLabel: string
  readonly maxLabel: string
}

/** A `mode: "scale"` rule declares a continuous spectrum (`scale_min`..`scale_max`
 * interpolating between its two `scale_tokens` endpoints) rather than discrete bands —
 * this renders that spectrum as a single gradient bar labelled with its two endpoints.
 * Auto (null) bounds resolve to the OBSERVED min/max the server computed for this
 * execution (`scale_legends`); only a rule the server produced no legend for (nothing to
 * measure, or an unresolvable reference) renders unbounded (±∞). */
export const deriveScaleGradients = (
  presentation: PresentationNode | null,
  scaleLegends: readonly ScaleLegendData[] = [],
): readonly ScaleGradientLegend[] => {
  if (!presentation) return []
  const gradients: ScaleGradientLegend[] = []
  for (const rule of presentation.stylingRules) {
    if (rule.mode !== 'scale' || rule.scaleTokens === null) continue
    const resolved = scaleLegends.find(
      (legend) => legend.capability === rule.capability && legend.attribute === rule.scaleAttribute,
    )
    const minimum = rule.scaleMin ?? resolved?.minimum ?? null
    const maximum = rule.scaleMax ?? resolved?.maximum ?? null
    gradients.push({
      capability: rule.capability,
      gradientCss: `linear-gradient(to right, ${tokenColor(rule.scaleTokens[0])}, ${tokenColor(rule.scaleTokens[1])})`,
      minLabel: minimum !== null ? String(minimum) : '−∞',
      maxLabel: maximum !== null ? String(maximum) : '∞',
    })
  }
  return gradients
}
