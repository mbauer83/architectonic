import { ref, computed, type Ref } from 'vue'
import { Effect, Exit, Cause, Option } from 'effect'
import { formatEffectError } from '../lib/errors'

export interface MutationHandle<A, E> {
  readonly result: Ref<A | null>
  readonly error: Ref<E | null>
  readonly running: Ref<boolean>
  readonly errorMessage: Ref<string | null>
  readonly run: (effect: Effect.Effect<A, E, never>) => Promise<Exit.Exit<A, E>>
  readonly reset: () => void
}

/**
 * Manages async mutation state. run() returns the Exit so callers can react to
 * success or failure without losing typed error information.
 */
export const useMutation = <A, E>(): MutationHandle<A, E> => {
  const result = ref<A | null>(null) as Ref<A | null>
  const error = ref<E | null>(null) as Ref<E | null>
  const running = ref(false)
  const causeString = ref<string | null>(null)

  const errorMessage = computed((): string | null =>
    error.value !== null ? formatEffectError(error.value) : causeString.value
  )

  const run = (effect: Effect.Effect<A, E, never>): Promise<Exit.Exit<A, E>> => {
    running.value = true
    error.value = null
    causeString.value = null
    return Effect.runPromiseExit(effect).then((exit) => {
      running.value = false
      Exit.match(exit, {
        onSuccess: (value) => { result.value = value },
        onFailure: (cause) => Option.match(Cause.failureOption(cause), {
          onSome: (e) => { error.value = e },
          onNone: () => { causeString.value = Cause.pretty(cause) },
        }),
      })
      return exit
    })
  }

  const reset = (): void => {
    result.value = null
    error.value = null
    causeString.value = null
    running.value = false
  }

  return { result, error, errorMessage, running, run, reset }
}
