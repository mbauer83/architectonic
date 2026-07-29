/**
 * Pure logic for the failure-mode matrix: how a cell reads, and in what order rows appear.
 *
 * Extracted so the rules that make this surface trustworthy are testable without mounting
 * anything. Three of them carry real weight:
 *
 * - `indeterminate` must never look like `low`. A row nobody has rated is a gap to close, and
 *   rendering it as a quiet band is how an un-analysed component comes to look safe.
 * - *Untouched* and *not credible* must be distinguishable at a glance. Both are empty of findings;
 *   only one of them has been looked at.
 * - Nothing here composes a score. The worklist is ordered, never rated.
 */

export interface FactorView {
  value: string | null
  basis: string
  basis_digest: string
  /** The digest of the model inputs the derived value came from. A judgement has to be filed
   *  against it, because one filed against a basis that has since moved no longer applies. */
  superseded: { value: string; author: string; justification: string } | null
}

export interface CellView {
  guideword: string
  state: 'untouched' | 'not-credible' | 'recorded'
  node_id: string | null
  action_priority: string
  occurrence_is_requested: boolean
  next_action: string
  dismissal: { by?: string; reason?: string }
  factors: Record<string, FactorView>
  occurrence_rationale_draft: string
  /** What the model already knows about this element, offered to whoever is about to judge its
   *  occurrence. Facts only — nothing in it proposes a rank, so a form may pre-fill the rationale
   *  and must never pre-fill the value. */
}

export interface RowView {
  element_id: string
  /** The element's reader-facing name, or '' when the architecture model cannot describe it. */
  element_name?: string
  /** The element's artifact type, or '' for the same reason. */
  element_type?: string
  nominated_by: string[]
  cells: CellView[]
  answered_cells: number
  unanswered_cells: number
  worst_action_priority: string | null
}

export const GUIDEWORD_LABELS: Record<string, string> = {
  'no-function': 'No function',
  'partial-function': 'Partial or degraded',
  'excessive-function': 'Excessive',
  'intermittent-function': 'Intermittent',
  'unintended-function': 'Unintended',
}

/** Reader-facing heading for a guideword, or the slug when it is one this build does not know. */
export function guidewordLabel(slug: string): string {
  return GUIDEWORD_LABELS[slug] ?? slug
}

/**
 * The class a cell paints with. `indeterminate` gets its own, distinct from every band — the one
 * confusion this grid must never permit is an unrated row reading as a low-priority one.
 */
export function cellClass(cell: CellView): string {
  if (cell.state === 'untouched') return 'cell-untouched'
  if (cell.state === 'not-credible') return 'cell-not-credible'
  return `cell-priority cell-${cell.action_priority}`
}

/** What a cell says at a glance. Never a number, and never blank for an unexamined cell. */
export function cellLabel(cell: CellView): string {
  if (cell.state === 'untouched') return 'Not examined'
  if (cell.state === 'not-credible') return 'Not credible'
  if (cell.action_priority === 'indeterminate') return 'Not yet rated'
  return cell.action_priority
}

/** Where a value came from, as a short glyph with the tooltip carrying the detail. */
export function basisGlyph(basis: string): string {
  if (basis === 'asserted') return '✎'
  if (basis === 'derived-superseding-an-assessment') return '↻'
  if (basis === 'derived') return '∴'
  return '–'
}

export function basisTooltip(factor: string, view: FactorView): string {
  if (view.basis === 'asserted') return `${factor} was asserted by a person`
  if (view.basis === 'derived') return `${factor} is derived from the model`
  if (view.basis === 'derived-superseding-an-assessment') {
    const previous = view.superseded
    const detail = previous
      ? ` A judgement of "${previous.value}" by ${previous.author} no longer applies: ${previous.justification}`
      : ''
    return `${factor} is derived; the model has changed since it was last judged.${detail}`
  }
  return `${factor} has no value yet`
}

/**
 * Which factors a cell shows a field for. Occurrence is omitted where it could not change the
 * band — asking for a judgement that cannot matter teaches people to answer carelessly, and those
 * same people then answer the rows where it does matter.
 */
export function visibleFactors(cell: CellView): string[] {
  const shown = ['severity', 'detectability']
  return cell.occurrence_is_requested ? ['severity', 'occurrence', 'detectability'] : shown
}

const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2, indeterminate: 3 }

/**
 * Worklist order: worst band first, then most unanswered cells, then by id so the list is stable.
 * An ordering, never a score — nothing derived here is displayed as a value.
 */
export function worklistOrder(rows: RowView[]): RowView[] {
  return [...rows].sort((a, b) => {
    const bandA = PRIORITY_ORDER[a.worst_action_priority ?? 'indeterminate'] ?? 4
    const bandB = PRIORITY_ORDER[b.worst_action_priority ?? 'indeterminate'] ?? 4
    if (bandA !== bandB) return bandA - bandB
    if (a.unanswered_cells !== b.unanswered_cells) return b.unanswered_cells - a.unanswered_cells
    return a.element_id.localeCompare(b.element_id)
  })
}

/** Progress across the whole matrix, counting a dismissal as an answer. */
export function coverageLine(rows: RowView[]): string {
  const answered = rows.reduce((total, row) => total + row.answered_cells, 0)
  const cells = rows.reduce((total, row) => total + row.cells.length, 0)
  if (cells === 0) return 'No candidate elements yet'
  return `${answered} of ${cells} cells answered across ${rows.length} element(s)`
}

/** Whether this cell is waiting for an occurrence judgement someone could record now.
 *
 * Three conditions, all of them the server's decisions rather than this view's: the cell has a
 * failure mode at all, occurrence is being asked for (it is suppressed where it cannot change the
 * band), and none has been recorded yet. */
export function awaitsOccurrence(cell: CellView): boolean {
  return (
    cell.state === 'recorded'
    && cell.occurrence_is_requested
    && (cell.factors.occurrence?.value ?? null) === null
  )
}

/** Whether *cell* is the one cell whose occurrence recorder is currently open.
 *
 * `openNodeId` is null when nothing is open, and a cell with no failure mode also has a null
 * `node_id`, so the two are never compared directly: an un-examined cell is not the open one. */
export function isRecordingCell(openNodeId: string | null, cell: Pick<CellView, 'node_id'>): boolean {
  return cell.node_id !== null && openNodeId === cell.node_id
}

/** The digest an occurrence judgement must be filed against, or '' when the cell has no basis. */
export function occurrenceBasisDigest(cell: CellView): string {
  return cell.factors.occurrence?.basis_digest ?? ''
}


/**
 * How a matrix row names its element.
 *
 * `TYPE: Name`, with the id kept as a secondary line. The row used to show the bare artifact id,
 * which is the one label that says nothing about which element an analyst is being asked to assess
 * — and with a hundred of them down the side, a column of ids reads as noise.
 *
 * The id is never dropped, only demoted: it is what an analyst quotes in a review and what every
 * other surface keys on. When the architecture model cannot describe the element the id is all
 * there is, so it becomes the heading again rather than being replaced by an invented label.
 */
export interface ElementHeading {
  /** The heading line, e.g. "application-component: Credential Backend". */
  primary: string
  /** The id, shown beneath — or '' when it is already the heading. */
  secondary: string
}

export function elementHeading(row: RowView): ElementHeading {
  const name = (row.element_name ?? '').trim()
  const type = (row.element_type ?? '').trim()
  if (!name) return { primary: row.element_id, secondary: '' }
  return {
    primary: type ? `${type}: ${name}` : name,
    secondary: row.element_id,
  }
}

/** An artifact id, as the row headings carry — `PREFIX@epoch.random[.slug]`. */
const ARTIFACT_ID = /^[A-Za-z]+@\d+\.[A-Za-z0-9_-]+(\..+)?$/

/**
 * Route to the architecture element a row is about, or null when the row does not name one.
 *
 * A row heading names a real model element, so it should reach it — reading a failure mode and
 * then having to search for the component it belongs to is the kind of dead end the matrix exists
 * to remove. Null rather than a broken link when `element_id` is not an artifact id: a row may be
 * nominated by content that has no page.
 */
export function elementRoute(row: RowView): string | null {
  const id = (row.element_id ?? '').trim()
  if (!ARTIFACT_ID.test(id)) return null
  return `/entity?id=${encodeURIComponent(id)}`
}
