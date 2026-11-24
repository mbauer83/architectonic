/**
 * The candidate architectures as a catalogue: each stack under the scope its root was started over,
 * each candidate below what it stacks on, as the list read names them.
 */
import type { CandidateSummary } from '../schemas/candidates'

/** One line of the catalogue: a candidate, and how deep it stacks under its group's root. */
export interface CatalogRow {
  readonly candidate: CandidateSummary
  readonly depth: number
}

/** The stacks whose roots were started over the same scope. */
export interface ScopeGroup {
  readonly scope: readonly string[]
  readonly rows: readonly CatalogRow[]
}

const byName = (a: CandidateSummary, b: CandidateSummary): number => a.name.localeCompare(b.name)

/**
 * Every candidate once: grouped by its root's scope, each root followed by what stacks on it, depth
 * first. A candidate whose parent is not listed is a root; one caught in a cycle is listed as a root
 * where the walk first meets it, so nothing is left out.
 */
export const catalogOf = (
  candidates: readonly CandidateSummary[],
): readonly ScopeGroup[] => {
  const known = new Set(candidates.map((one) => one.id))
  const children = new Map<string, CandidateSummary[]>()
  for (const one of candidates) {
    if (one.parent && known.has(one.parent)) children.set(one.parent, [...(children.get(one.parent) ?? []), one])
  }
  const seen = new Set<string>()
  const walk = (root: CandidateSummary, depth: number): CatalogRow[] => {
    if (seen.has(root.id)) return []
    seen.add(root.id)
    return [{ candidate: root, depth },
      ...[...(children.get(root.id) ?? [])].sort(byName).flatMap((child) => walk(child, depth + 1))]
  }
  const roots = candidates.filter((one) => !one.parent || !known.has(one.parent)).sort(byName)
  const groups = new Map<string, { scope: readonly string[]; rows: CatalogRow[] }>()
  for (const root of [...roots, ...[...candidates].sort(byName)]) {
    const rows = walk(root, 0)
    if (!rows.length) continue
    const scope = [...root.scope].sort()
    const key = scope.join('\n')
    const group = groups.get(key) ?? { scope, rows: [] }
    group.rows.push(...rows)
    groups.set(key, group)
  }
  return [...groups.values()]
}

/** A group's heading: what its roots were started over. */
export const scopeLabel = (scope: readonly string[]): string =>
  scope.length === 0
    ? 'No scope: started empty'
    : `Scope of ${scope.length} element${scope.length === 1 ? '' : 's'}`
