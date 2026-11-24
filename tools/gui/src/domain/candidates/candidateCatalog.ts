/**
 * The candidate architectures as a catalogue: each stack under the scope its root was started over,
 * each candidate below what it stacks on. A candidate's scope and its operations are read off its
 * record (`changes_read_candidate`); the list read names only what each stacks on.
 */
import type { CandidateSummary } from '../schemas/candidates'

/** What a candidate's record says beyond its summary. */
export interface CandidateFacts {
  /** The model's entities it is read over, by id; empty for one started empty or stacked on another. */
  readonly scope: readonly string[]
  readonly operations: number
}

const strings = (value: unknown): readonly string[] =>
  Array.isArray(value) ? value.filter((one): one is string => typeof one === 'string') : []

/** A candidate's scope and how many operations it records, read off its recorded form. */
export const factsOf = (record: Readonly<Record<string, unknown>>): CandidateFacts => {
  const changes = record.changes
  const operations = typeof changes === 'object' && changes !== null && 'operations' in changes
    && Array.isArray(changes.operations) ? changes.operations.length : 0
  return { scope: strings(record.scope), operations }
}

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
  candidates: readonly CandidateSummary[], facts: ReadonlyMap<string, CandidateFacts>,
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
    const scope = [...(facts.get(root.id)?.scope ?? [])].sort()
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
    ? 'No scope: started empty, or scope not read yet'
    : `Scope of ${scope.length} element${scope.length === 1 ? '' : 's'}`
