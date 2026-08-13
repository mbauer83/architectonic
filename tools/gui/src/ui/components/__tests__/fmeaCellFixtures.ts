/** Matrix cells as the server sends them, shared by the recorder's tests.
 *
 * A sample of the scale rather than an import of it: the vocabulary is served with the matrix, and a
 * test asserting that nothing pre-fills a value must not depend on the client knowing the members.
 */
import type { CellView } from '../../views/AssuranceFmeaView.helpers'

export const OCCURRENCE_SCALE_SAMPLE = ['rare', 'unlikely', 'occasional', 'likely', 'frequent']

export function cellAwaitingOccurrence(overrides: Partial<CellView> = {}): CellView {
  return {
    guideword: 'no-function',
    state: 'recorded',
    node_id: 'FMD@1',
    action_priority: 'indeterminate',
    occurrence_is_requested: true,
    next_action: 'Record an occurrence with a rationale; the band cannot be decided without it.',
    // Both fields, empty: the route sends a dismissal on every cell, not only a dismissed one.
    dismissal: { by: '', reason: '' },
    factors: {
      severity: { value: 'major', basis: 'derived', basis_digest: 'sev-1', assessment: null, superseded: null },
      occurrence: { value: null, basis: 'absent', basis_digest: 'occ-1', assessment: null, superseded: null },
      detectability: { value: 'low', basis: 'derived', basis_digest: 'det-1', assessment: null, superseded: null },
    },
    occurrence_rationale_draft:
      '- nothing can stand in for it — 3 dependent(s) rely on it alone\n'
      + '- APP@1 accesses DOB@2, classified Confidential',
    ...overrides,
  }
}
