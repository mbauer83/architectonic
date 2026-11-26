/**
 * Several candidate architectures read against one common base, so their differences can be laid
 * side by side: which candidates are compared, which bases they share, and which elements more than
 * one of them changes. Whether their operations conflict is the server's integration check; this
 * only pairs the comparisons each candidate already has.
 */
import type { CandidateComparison, ChangeDifference, CandidateSummary } from '../schemas/candidates'
import { stableEntityId } from '../artifactId'
import type { Marks } from './elementMarks'
import { type BaseChoice, chainOf } from './candidateStack'

/** The compared candidates as an address carries them: each once, in the order first named. */
export const comparedIds = (values: readonly unknown[]): readonly string[] =>
  [...new Set(values.filter((one): one is string => typeof one === 'string' && one !== ''))]

/**
 * The bases every compared candidate may be read against: the model, then each candidate all of
 * them stack on (never one of the compared themselves), from the model upwards.
 */
export const sharedBases = (ids: readonly string[], all: readonly CandidateSummary[]): readonly BaseChoice[] => {
  const beneath = ids.map((id) => chainOf(id, all).slice(1))
  const shared = (beneath[0] ?? []).filter((one) =>
    !ids.includes(one.id) && beneath.every((chain) => chain.some((other) => other.id === one.id)))
  return [
    { value: 'model', label: 'the current model' },
    ...[...shared].reverse().map((one) => ({ value: one.id, label: one.name })),
  ]
}

/** The base a comparison reads against: *asked* where all may share it, else the nearest shared one. */
export const commonBase = (ids: readonly string[], all: readonly CandidateSummary[], asked = ''): string => {
  const choices = sharedBases(ids, all)
  return choices.some((one) => one.value === asked) ? asked : (choices.at(-1)?.value ?? 'model')
}

/** One compared candidate's differences from the common base, under its id. */
export interface ComparedDiff {
  readonly id: string
  readonly diff: readonly ChangeDifference[]
}

/**
 * The elements more than one compared candidate changes, by stable id, each with the other
 * candidates that change it as well. A changed relation is not counted, as `diffMarks` marks neither end.
 */
export const changedByOthers = (
  compared: readonly ComparedDiff[],
): ReadonlyMap<string, ReadonlyMap<string, readonly string[]>> => {
  const changers = new Map<string, Set<string>>()
  for (const { id, diff } of compared) {
    for (const row of diff) {
      if (typeof row.target !== 'string') continue
      const key = stableEntityId(row.target)
      changers.set(key, (changers.get(key) ?? new Set()).add(id))
    }
  }
  return new Map(compared.map(({ id }) => [id, new Map([...changers]
    .filter(([, by]) => by.size > 1 && by.has(id))
    .map(([element, by]) => [element, [...by].filter((other) => other !== id)] as const))]))
}

/** *marks*, with each element another candidate also changes saying so in its title. */
export const withOthers = (
  marks: Marks, others: ReadonlyMap<string, readonly string[]>, nameOf: (id: string) => string,
): Marks =>
  new Map([...marks].map(([element, mark]) => {
    const also = others.get(element)
    return [element, also?.length
      ? { ...mark, title: `${mark.title} · also changed in ${also.map(nameOf).join(', ')}` }
      : mark]
  }))

/** What an element is called while the comparisons that name it are still being read. */
export const UNNAMED_YET = '…'

/**
 * An element by its name in the common base, as the compared candidates' comparisons read it: the name a
 * change had before, else the name a composed view gives it. While a comparison is still being read the name
 * may yet arrive, so the element is called `UNNAMED_YET` rather than by its id; only once every comparison is
 * read does an element none of them names stand as its id.
 */
export const elementNameIn = (readings: readonly (CandidateComparison | null)[], id: string): string => {
  const key = stableEntityId(id)
  const read = readings.filter((one): one is CandidateComparison => one !== null)
  const before = read.flatMap((one) => one.diff)
    .filter((row) => row.kind === 'entity' && typeof row.target === 'string' && stableEntityId(row.target) === key)
    .map((row) => row.fields.name?.before).find((name) => typeof name === 'string')
  const named = read.flatMap((one) => one.view.entities)
    .find((one) => stableEntityId(one.artifact_id ?? one.id) === key)?.fields.name
  const name = typeof before === 'string' ? before : typeof named === 'string' ? named : null
  return name ?? (read.length < readings.length ? UNNAMED_YET : id)
}
