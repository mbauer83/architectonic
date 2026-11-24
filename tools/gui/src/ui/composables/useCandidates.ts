/**
 * The analysis's candidate architectures: the naive architecture and what stacks on it, the one
 * being read, and its comparison with the base chosen in *against* — by default its parent (Q38).
 */
import { computed, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { CandidateComparison, CandidateSummary } from '../../domain/schemas/candidates'
import { analysisCandidates, baseChoices, defaultBase } from '../../domain/stressAnalysis/candidateStack'
import { formatEffectError } from '../lib/errors'

export function useCandidates(svc: ModelService, naiveId: () => string, scopeDiagram: () => string) {
  const all = shallowRef<readonly CandidateSummary[]>([])
  const selected = ref<string | null>(null)
  const against = ref('model')
  const comparison = shallowRef<CandidateComparison | null>(null)
  const error = ref<string | null>(null)

  const inAnalysis = computed(() => analysisCandidates(naiveId(), all.value))
  const choices = computed(() => selected.value ? baseChoices(selected.value, inAnalysis.value, all.value) : [])

  const compare = async (): Promise<void> => {
    const id = selected.value
    if (!id) return
    try {
      const read = await Effect.runPromise(svc.compareCandidate(id, against.value, scopeDiagram() || undefined))
      if (selected.value === id) comparison.value = read
      error.value = null
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  }

  const load = async (): Promise<void> => {
    try {
      all.value = await Effect.runPromise(svc.listCandidates())
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  }

  /** Read *id*, against its parent. */
  const select = async (id: string): Promise<void> => {
    if (selected.value !== id) comparison.value = null
    selected.value = id
    against.value = defaultBase(id, all.value)
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
      error.value = formatEffectError(failure)
      return false
    }
  }

  /** A new candidate stacked on *parent* (*New candidate on top…*); answers its id. */
  const stackOn = async (parent: string, name: string): Promise<string | null> => {
    try {
      const created = await Effect.runPromise(svc.createCandidate({ name, parent }))
      await load()
      const id = String(created.record.id)
      await select(id)
      return id
    } catch (failure) {
      error.value = formatEffectError(failure)
      return null
    }
  }

  return { all, selected, against, comparison, error, inAnalysis, choices, load, select, compareWith, stackOn, rebase }
}

export type Candidates = ReturnType<typeof useCandidates>
