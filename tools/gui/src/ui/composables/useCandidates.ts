/**
 * Candidate architectures as a reader works with them: every candidate, the stack of one root and what
 * stacks on it, the one being read, and its comparison with the base chosen in *against* — by default
 * its parent (Q38). Independent of any analysis: a stress analysis supplies its naive architecture as
 * the root and its scope diagram; the candidate pages supply none and read the selected candidate's
 * own stack, down to the candidate that stacks on the model.
 */
import { type ShallowRef, computed, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { CandidateComparison, CandidateSummary } from '../../domain/schemas/candidates'
import { baseChoices, defaultBase, rootOf, stackFrom } from '../../domain/candidates/candidateStack'
import { formatEffectError } from '../lib/errors'

export interface CandidateReading {
  /** The stack's root; by default the bottom of the selected candidate's stack. */
  readonly root?: () => string
  /** The stored diagram whose drawing a comparison carries; none for no drawing. */
  readonly scopeDiagram: () => string
  /** Every candidate, held with other readings so that several of them list once; by default its own. */
  readonly all?: ShallowRef<readonly CandidateSummary[]>
}

/** What the composable reads and writes through: the model service's candidate half. */
export type CandidateAccess = Pick<ModelService,
  'listCandidates' | 'createCandidate' | 'readCandidate' | 'rebaseCandidate' | 'compareCandidate' | 'deleteCandidate'>

export function useCandidates(svc: CandidateAccess, reading: CandidateReading) {
  const all = reading.all ?? shallowRef<readonly CandidateSummary[]>([])
  const selected = ref<string | null>(null)
  const against = ref('model')
  const comparison = shallowRef<CandidateComparison | null>(null)
  const error = ref<string | null>(null)

  const root = computed(() => reading.root?.() ?? (selected.value ? rootOf(selected.value, all.value) : ''))
  const inStack = computed(() => stackFrom(root.value, all.value))
  const choices = computed(() => selected.value ? baseChoices(selected.value, inStack.value, all.value) : [])

  const failed = (failure: unknown): void => {
    error.value = formatEffectError(failure)
  }

  const compare = async (): Promise<void> => {
    const id = selected.value
    const base = against.value
    if (!id) return
    try {
      const read = await Effect.runPromise(svc.compareCandidate(id, base, reading.scopeDiagram() || undefined))
      if (selected.value === id && against.value === base) comparison.value = read
      error.value = null
    } catch (failure) {
      failed(failure)
    }
  }

  const load = async (): Promise<void> => {
    try {
      all.value = await Effect.runPromise(svc.listCandidates())
    } catch (failure) {
      failed(failure)
    }
  }

  /** Read *id* against *base*: by default its parent. */
  const select = async (id: string, base = defaultBase(id, all.value)): Promise<void> => {
    if (selected.value !== id) comparison.value = null
    selected.value = id
    against.value = base
    await compare()
  }

  const compareWith = async (base: string): Promise<void> => {
    against.value = base
    await compare()
  }

  /** Write *id*'s drifted operations again against the model as it stands now, then read it again. */
  const rebase = async (id: string): Promise<boolean> => {
    try {
      const { version } = await Effect.runPromise(svc.readCandidate(id))
      await Effect.runPromise(svc.rebaseCandidate(id, version))
      await compare()
      return true
    } catch (failure) {
      failed(failure)
      return false
    }
  }

  /**
   * A new candidate from *record* — a name, and a parent or a scope, or neither for one that starts
   * empty — or scoped to what *diagram* draws. Answers its id, and lists it.
   */
  const create = async (record: Readonly<Record<string, unknown>>, diagram?: string): Promise<string | null> => {
    try {
      const created = await Effect.runPromise(svc.createCandidate(record, diagram))
      await load()
      return String(created.record.id)
    } catch (failure) {
      failed(failure)
      return null
    }
  }

  /** A new candidate stacked on *parent* (*New candidate on top…*), then read; answers its id. */
  const stackOn = async (parent: string, name: string): Promise<string | null> => {
    const id = await create({ name, parent })
    if (id) await select(id)
    return id
  }

  /** Delete *id*; the server refuses, saying why, while one stacks on it or an analysis starts from it. */
  const remove = async (id: string): Promise<boolean> => {
    try {
      await Effect.runPromise(svc.deleteCandidate(id))
      if (selected.value === id) {
        selected.value = null
        comparison.value = null
      }
      await load()
      error.value = null
      return true
    } catch (failure) {
      failed(failure)
      return false
    }
  }

  return {
    all, selected, against, comparison, error, root, inStack, choices,
    load, select, compareWith, create, stackOn, rebase, remove,
  }
}

export type Candidates = ReturnType<typeof useCandidates>
