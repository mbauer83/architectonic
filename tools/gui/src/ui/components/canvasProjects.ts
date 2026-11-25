/**
 * The projects a new element on a diagram may be filed into (sketch 03·3, Q18): every project one may
 * file into, those holding most of this diagram's elements first, the first of them preselected. A tie
 * keeps the order the server gives, which is the curated order the sidebar shows.
 */
import type { GroupEntry, GroupList } from '../../domain/schemas/groups'
import { filableCollections } from '../lib/collectionAxes'

export const projectsByUse = (
  list: GroupList | null, drawnIn: Iterable<string | undefined>,
): readonly GroupEntry[] => {
  const held = new Map<string, number>()
  for (const group of drawnIn) if (group !== undefined) held.set(group, (held.get(group) ?? 0) + 1)
  const uses = (entry: GroupEntry): number => held.get(entry.slug) ?? 0
  return [...filableCollections(list, 'model-project')].sort((one, other) => uses(other) - uses(one))
}
