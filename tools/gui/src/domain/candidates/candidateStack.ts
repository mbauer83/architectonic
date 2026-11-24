/**
 * Candidate architectures as a stack: what each sits on down to the model, which candidates stack on a
 * root, and what a candidate may be compared with (Q38: any depth; never itself, never one stacked on
 * it; by default its parent). A stress analysis's root is its naive architecture; nothing here knows that.
 */
import type { CandidateSummary } from '../schemas/candidates'

const byId = (candidates: readonly CandidateSummary[]) => new Map(candidates.map((one) => [one.id, one]))

/** *id* and what it stacks on, nearest first, ending above the model; a cycle ends the walk. */
export const chainOf = (id: string, candidates: readonly CandidateSummary[]): readonly CandidateSummary[] => {
  const known = byId(candidates)
  const chain: CandidateSummary[] = []
  for (let at = known.get(id); at && !chain.includes(at); at = at.parent ? known.get(at.parent) : undefined) {
    chain.push(at)
  }
  return chain
}

/** Every candidate stacked on *id*, at any depth. */
export const descendantsOf = (id: string, candidates: readonly CandidateSummary[]): ReadonlySet<string> =>
  new Set(candidates.filter((one) => one.id !== id && chainOf(one.id, candidates).some((c) => c.id === id))
    .map((one) => one.id))

/** *root* and everything stacked on it, nearest the model first; nothing for an unknown root. */
export const stackFrom = (
  root: string, candidates: readonly CandidateSummary[],
): readonly CandidateSummary[] => {
  const below = descendantsOf(root, candidates)
  return candidates.filter((one) => one.id === root || below.has(one.id))
    .sort((a, b) => chainOf(a.id, candidates).length - chainOf(b.id, candidates).length)
}

/** "stacks on X ← Naive architecture ← the current model", read from *id*'s parent down. */
export const stackLine = (id: string, candidates: readonly CandidateSummary[]): string =>
  ['stacks on', [...chainOf(id, candidates).slice(1).map((one) => one.name), 'the current model'].join(' ← ')]
    .join(' ')

/** One choice of *against*: its value in the selector, and its words. */
export interface BaseChoice {
  readonly value: string
  readonly label: string
}

/** What *id* may be compared with: the model, then the stack's other candidates not stacked on it. */
export const baseChoices = (
  id: string, inStack: readonly CandidateSummary[], all: readonly CandidateSummary[],
): readonly BaseChoice[] => {
  const above = descendantsOf(id, all)
  return [
    { value: 'model', label: 'the current model' },
    ...inStack
      .filter((one) => one.id !== id && !above.has(one.id))
      .map((one) => ({ value: one.id, label: one.name })),
  ]
}

/** The default base: the candidate's parent, or the model for one that stacks on nothing. */
export const defaultBase = (id: string, candidates: readonly CandidateSummary[]): string =>
  byId(candidates).get(id)?.parent ?? 'model'

/** The candidate at the bottom of *id*'s stack, the one that stacks on the model; *id* if unknown. */
export const rootOf = (id: string, candidates: readonly CandidateSummary[]): string =>
  chainOf(id, candidates).at(-1)?.id ?? id
