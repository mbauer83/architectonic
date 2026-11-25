/**
 * *Apply as a target state…*, *Move into the baseline…* and *Withdraw…* on a candidate's page: where the candidate's
 * target state stands (read off its record), and for either write a dry run first, then the write once its
 * reader confirms. The server generates, judges and writes the operations; this only sequences the calls.
 *
 * *onWritten* is told which write landed, before the confirmation closes, so the page that owns the
 * candidate can read it again: the confirmation is gone by the time it could say so.
 */
import { ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { OperationStanding, TargetStateIds } from '../../domain/schemas/candidates'
import { targetStateOf } from '../../domain/candidates/candidateTargetState'
import { formatEffectError } from '../lib/errors'

export type CandidateTargetStateAccess = Pick<
  ModelService, 'applyCandidateAsTargetState' | 'moveCandidateIntoBaseline' | 'withdrawCandidateTargetState'
  | 'readCandidate'
>

/** Which of the three writes a confirmation is for. */
export type TargetWrite = 'apply' | 'move' | 'withdraw'

/** A dry run being confirmed: what it would write, and the refusal when there is one. */
export interface TargetPreview {
  readonly write: TargetWrite
  readonly candidate: string
  readonly operations: readonly Readonly<Record<string, unknown>>[]
  readonly standing: readonly OperationStanding[]
  readonly refusal: string | null
  /** For an apply: where the target state would stand. */
  readonly ids: TargetStateIds | null
  /** For an apply: the types of elements a plateau may not hold. */
  readonly unheld: readonly string[]
}

type Answer = Omit<TargetPreview, 'write' | 'candidate'> & { readonly written: boolean }

export function useCandidateTargetState(
  svc: CandidateTargetStateAccess, onWritten: (write: TargetWrite) => void = () => {},
) {
  /** Where the candidate's target state stands; null when it is not in the model as one. */
  const standing = shallowRef<TargetStateIds | null>(null)
  const preview = shallowRef<TargetPreview | null>(null)
  const busy = ref(false)
  const error = ref<string | null>(null)

  const run = async <T>(call: () => Promise<T>): Promise<T | null> => {
    busy.value = true
    try {
      const answer = await call()
      error.value = null
      return answer
    } catch (failure) {
      error.value = formatEffectError(failure)
      return null
    } finally {
      busy.value = false
    }
  }

  /** Each write's answer, read the same way: whether it landed, and what it would write. */
  const asked: Record<TargetWrite, (id: string, dryRun: boolean) => Effect.Effect<Answer, unknown>> = {
    apply: (id, dryRun) => svc.applyCandidateAsTargetState(id, dryRun).pipe(Effect.map((answer): Answer => ({
      written: answer.applied, ids: answer.target_state ?? null, unheld: answer.unheld ?? [],
      operations: answer.operations ?? [], standing: answer.standing, refusal: answer.refusal ?? null,
    }))),
    move: (id, dryRun) => svc.moveCandidateIntoBaseline(id, dryRun).pipe(Effect.map((answer): Answer => ({
      written: answer.integrated, ids: null, unheld: [],
      operations: answer.operations ?? [], standing: answer.standing, refusal: answer.refusal ?? null,
    }))),
    withdraw: (id, dryRun) => svc.withdrawCandidateTargetState(id, dryRun).pipe(Effect.map((answer): Answer => ({
      written: answer.released, ids: null, unheld: [],
      operations: answer.operations ?? [], standing: [], refusal: answer.refusal ?? null,
    }))),
  }
  const ask = (write: TargetWrite, id: string, dryRun: boolean): Promise<Answer> =>
    Effect.runPromise(asked[write](id, dryRun))

  /** Read where *id*'s target state stands. */
  const load = async (id: string): Promise<void> => {
    const read = await Effect.runPromise(svc.readCandidate(id)).catch(() => null)
    standing.value = read ? targetStateOf(read.record) : null
  }

  /** Ask what *write* would do to *id*; nothing is written. */
  const open = async (write: TargetWrite, id: string): Promise<void> => {
    preview.value = null
    const answer = await run(() => ask(write, id, true))
    if (!answer) return
    const { written: _written, ...shown } = answer
    preview.value = { write, candidate: id, ...shown }
  }

  const close = (): void => {
    preview.value = null
    error.value = null
  }

  /** Write what is previewed; answers whether it landed. A refusal stays open, saying why. */
  const confirm = async (): Promise<boolean> => {
    const shown = preview.value
    if (!shown) return false
    const answer = await run(() => ask(shown.write, shown.candidate, false))
    if (!answer?.written) return false
    await load(shown.candidate)
    onWritten(shown.write)
    preview.value = null
    return true
  }

  return { standing, preview, busy, error, load, open, close, confirm }
}

export type CandidateTargetState = ReturnType<typeof useCandidateTargetState>
