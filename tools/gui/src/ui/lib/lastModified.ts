/**
 * Rendering the `last_updated` stamp browse lists carry.
 *
 * The stored value is a canonical UTC instant (`2026-07-24T09:15:00Z`), which is precise but
 * not readable in a table cell. It is displayed as-is in UTC rather than converted to the
 * viewer's timezone: two people comparing "when did this change" across a shared repository
 * should read the same number, and the stamp's whole purpose is ordering.
 *
 * Repositories that predate the time component carry a date only; that shortens the cell
 * instead of inventing a midnight that was never recorded.
 */

/** Shown when an artifact carries no stamp at all — not "never modified", just unrecorded. */
export const NO_STAMP = '—'

const CANONICAL = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}):\d{2}Z$/
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

/** The cell text: `YYYY-MM-DD HH:MM` (UTC), a bare date, or the placeholder. */
export const formatLastModified = (stamp: string | null | undefined): string => {
  if (!stamp) return NO_STAMP
  const canonical = CANONICAL.exec(stamp)
  if (canonical) return `${canonical[1]} ${canonical[2]}`
  if (DATE_ONLY.test(stamp)) return stamp
  return stamp
}

/** The cell's tooltip: the exact stored instant, so precision is never lost to formatting. */
export const lastModifiedTitle = (stamp: string | null | undefined): string | undefined =>
  stamp ? `Last modified ${stamp} (UTC)` : 'No modification stamp recorded'
