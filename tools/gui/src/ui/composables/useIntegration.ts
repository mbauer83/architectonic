/**
 * Integrating candidates (06·7, S4): the chosen candidates, the integration's name, and the resolutions the
 * author has made so far, in order. Every change asks the server for a dry run over all of them, so the
 * conflicts shown are always those still standing after the resolutions made; *Integrate* writes the new
 * candidate once none stands. Taking a resolution back asks again without it.
 *
 * *Raise a decision* drafts an ADR through the document create: the conflict stays until a side is taken,
 * an operation dropped or a value merged.
 */
import { computed, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { CandidateIntegration, IntegrationConflict, Resolution } from '../../domain/schemas/candidates'
import { type DecisionOption, type NameOf, decisionDraft } from '../../domain/candidates/integration'
import { formatEffectError } from '../lib/errors'

export type IntegrationAccess = Pick<ModelService, 'integrateCandidates' | 'createDocument'>

export function useIntegration(svc: IntegrationAccess, onIntegrated: (id: string) => void) {
  const chosen = ref<readonly string[]>([])
  const name = ref('Integration')
  const resolutions = shallowRef<readonly Resolution[]>([])
  /** What each resolution was about, in words, as it was made. */
  const abouts = shallowRef<readonly string[]>([])
  const answer = shallowRef<CandidateIntegration | null>(null)
  const busy = ref(false)
  const error = ref<string | null>(null)
  /** The draft ADR raised about each conflict, by subject. */
  const decisions = shallowRef<ReadonlyMap<string, string>>(new Map())

  const ask = async (dryRun: boolean): Promise<CandidateIntegration | null> => {
    busy.value = true
    error.value = null
    try {
      return await Effect.runPromise(svc.integrateCandidates({
        candidates: chosen.value, name: name.value.trim() || 'Integration', resolutions: resolutions.value,
        dry_run: dryRun,
      }))
    } catch (failure) {
      error.value = formatEffectError(failure)
      return null
    } finally {
      busy.value = false
    }
  }

  /** The conflicts standing between the chosen candidates, after the resolutions made. */
  const check = async (): Promise<void> => {
    answer.value = chosen.value.length > 1 ? await ask(true) : null
  }

  /** *resolution*, about what *about* says, made after the others; not kept where the server refuses it. */
  const resolve = async (resolution: Resolution, about = resolution.subject): Promise<void> => {
    const before = resolutions.value
    resolutions.value = [...before, resolution]
    const read = await ask(true)
    if (read) {
      answer.value = read
      abouts.value = [...abouts.value.slice(0, before.length), about]
    } else resolutions.value = before
  }

  /** The resolution at *index* taken back, with every one made after it, which was made over it. */
  const takeBack = async (index: number): Promise<void> => {
    resolutions.value = resolutions.value.slice(0, index)
    abouts.value = abouts.value.slice(0, index)
    await check()
  }

  const choose = async (ids: readonly string[]): Promise<void> => {
    chosen.value = ids
    resolutions.value = []
    abouts.value = []
    await check()
  }

  const ready = computed(() => answer.value !== null && answer.value.conflicts.length === 0 && !busy.value)

  const integrate = async (): Promise<void> => {
    const written = await ask(false)
    const id = written?.integration?.record.id
    if (typeof id !== 'string') return
    resolutions.value = []
    abouts.value = []
    answer.value = null
    onIntegrated(id)
  }

  /** A draft ADR about *conflict*, its options what each party proposes; the conflict stays open. */
  const raiseDecision = async (
    conflict: IntegrationConflict, options: readonly DecisionOption[], nameOf: NameOf,
  ) => {
    const { title, body } = decisionDraft(conflict, options, nameOf)
    try {
      const written = await Effect.runPromise(svc.createDocument({
        doc_type: 'adr', title, body, status: 'draft', dry_run: false,
      }))
      decisions.value = new Map([...decisions.value, [conflict.subject, written.artifact_id]])
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  }

  /** The name the new candidate is given. */
  const rename = (text: string): void => { name.value = text }

  return {
    chosen, name, resolutions, abouts, answer, busy, error, decisions, ready,
    check, choose, resolve, takeBack, integrate, raiseDecision, rename,
  }
}

export type Integration = ReturnType<typeof useIntegration>
