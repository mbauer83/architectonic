import { ref, computed, type Ref } from 'vue'
import { Effect, Exit, Cause, Option } from 'effect'
import { formatEffectError } from '../lib/errors'

export interface QueryHandle<A, E> {
  readonly data: Ref<A | null>
  readonly error: Ref<E | null>
  readonly loading: Ref<boolean>
  readonly errorMessage: Ref<string | null>
  readonly run: (effect: Effect.Effect<A, E, never>) => void
  readonly reset: () => void
}

/**
 * Manages async read state with stale-result suppression.
 * Each run() supersedes in-flight calls — only the latest result writes to state.
 */
export const useQuery = <A, E>(): QueryHandle<A, E> => {
  const data = ref<A | null>(null) as Ref<A | null>
  const error = ref<E | null>(null) as Ref<E | null>
  const loading = ref(false)
  const causeString = ref<string | null>(null)
  let generation = 0

  const errorMessage = computed((): string | null =>
    error.value !== null ? formatEffectError(error.value) : causeString.value
  )

  const run = (effect: Effect.Effect<A, E, never>): void => {
    const gen = ++generation
    loading.value = true
    error.value = null
    causeString.value = null
    void Effect.runPromiseExit(effect).then((exit) => {
      if (gen !== generation) return
      loading.value = false
      Exit.match(exit, {
        onSuccess: (value) => { data.value = value },
        onFailure: (cause) => Option.match(Cause.failureOption(cause), {
          onSome: (e) => { error.value = e },
          onNone: () => { causeString.value = Cause.pretty(cause) },
        }),
      })
    })
  }

  const reset = (): void => {
    generation++
    data.value = null
    error.value = null
    causeString.value = null
    loading.value = false
  }

  return { data, error, loading, errorMessage, run, reset }
}
