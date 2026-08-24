/**
 * Which of the index page's states a store-wide security-signal read puts it in.
 *
 * Pure, so the distinction that matters is testable without a browser: **nothing ingested** and
 * **snapshots that assess no entity** are different situations with different next steps, and a
 * single "nothing here" would send a reader to the wrong one.
 */
import type { SecuritySignalStats } from '../../domain/schemas/assurance-security'

export type IndexState =
  | { kind: 'limited'; reason: string }
  | { kind: 'no-snapshots' }
  | { kind: 'no-assessed-entities'; snapshots: number }
  | { kind: 'anchors' }

/**
 * `reason` wins: a caller told why the numbers are absent must not also be told the store is empty,
 * which is a claim about the store rather than about their view of it.
 */
export const indexState = (stats: SecuritySignalStats): IndexState => {
  const reason = stats.reason ?? ''
  if (reason) return { kind: 'limited', reason }
  if ((stats.assessed_entities ?? []).length > 0) return { kind: 'anchors' }
  const snapshots = stats.total_snapshots ?? 0
  return snapshots === 0 ? { kind: 'no-snapshots' } : { kind: 'no-assessed-entities', snapshots }
}
