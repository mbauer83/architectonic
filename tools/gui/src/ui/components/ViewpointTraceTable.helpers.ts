/**
 * Pure projection of a coverage trace table into renderable columns and cells.
 *
 * Kept free of Vue so the honesty rules are unit-testable: a diagnostic observation must never
 * render in a verdict column or carry verdict styling, and every cell shows TEXT rather than a
 * bare colour — a reader must be able to tell `none_observed` (nothing was looked for here)
 * from `gap` (something required is missing) without decoding a palette.
 */
import type { PatternResult, TraceRow, TraceTable } from '../../domain/schemas/viewpoints'

/** Visual weight only. `neutral` is the deliberate home of verdict-free observations. */
export type CellTone = 'positive' | 'negative' | 'neutral'

export interface TraceColumn {
  readonly key: string
  readonly label: string
  readonly role: 'authoritative' | 'diagnostic'
}

export interface TraceCell {
  readonly text: string
  readonly detail: string
  readonly tone: CellTone
}

export interface TraceDisplayRow {
  readonly entityId: string
  readonly name: string
  readonly type: string
  readonly verdict: string
  readonly tone: CellTone
  readonly cells: readonly TraceCell[]
}

/** Every row carries the same patterns in declaration order, so the first row fixes the layout. */
export function traceColumns(table: TraceTable | null): readonly TraceColumn[] {
  const first = table?.rows[0]
  if (!first) return []
  return first.pattern_results.map(([name, result]: readonly [string, PatternResult]) => ({
    key: name,
    label: humanizePatternName(name),
    role: result.role,
  }))
}

export function humanizePatternName(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

export function verdictTone(verdict: string): CellTone {
  if (verdict === 'gap') return 'negative'
  return verdict === 'pass' ? 'positive' : 'neutral'
}

function cellFor(result: PatternResult): TraceCell {
  if (result.role === 'diagnostic') {
    // No verdict tone: an absent observation is not a failure, and colouring it like one is
    // exactly the false-gap this view exists to avoid.
    return {
      text: result.observation.replace(/_/g, ' '),
      detail: result.last_satisfied_ids.length ? `${result.last_satisfied_ids.length} realizer(s)` : '',
      tone: 'neutral',
    }
  }
  const { covered, applicable } = result.coverage
  const missing = result.missing_expected.length ? ` · missing ${result.missing_expected.join(', ')}` : ''
  return {
    text: `${result.status_code.replace(/_/g, ' ')} ${covered}/${applicable}`,
    detail: `${result.verdict}${missing}`,
    tone: verdictTone(result.verdict),
  }
}

export function traceDisplayRows(table: TraceTable | null): readonly TraceDisplayRow[] {
  if (!table) return []
  return table.rows.map((row: TraceRow) => ({
    entityId: row.entity_id,
    name: row.name,
    type: row.entity_type,
    verdict: row.verdict,
    tone: verdictTone(row.verdict),
    cells: row.pattern_results.map(([, result]: readonly [string, PatternResult]) => cellFor(result)),
  }))
}

/**
 * A truncated table must say so: `total_rows` counts the applicable population BEFORE the page
 * limit, so a gap beyond the page still exists even though no row shows it.
 */
export function traceTruncationNote(table: TraceTable | null): string {
  if (!table || !table.truncated) return ''
  return (
    `Showing ${table.returned_rows} of ${table.total_rows} rows — ` +
    'narrow the scope or raise the limit to see the rest.'
  )
}

/** Coverage rests on a bounded traversal; if that traversal was cut short the numbers are a floor. */
export function traceDerivationNote(table: TraceTable | null): string {
  if (!table || !table.derived_truncated) return ''
  return 'Realization search hit its budget — coverage shown is a lower bound, not a final verdict.'
}
