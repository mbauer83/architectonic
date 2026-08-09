import { onScopeDispose, ref, type Ref } from 'vue'
import { SAVE_DEBOUNCE_MS } from './useScratchpadDocument'

/**
 * One save per idle period, never one per gesture.
 *
 * A canvas produces events continuously — every drag emits a stream of positions — while the
 * repository behind this is a git working tree behind a mutation gate and a write queue. Writing
 * per gesture would put thousands of small writes through a path built for deliberate edits, and
 * that is the class of problem the previous release was spent on.
 *
 * So the collection happens **here, in the browser, before any request is issued**. A server-side
 * debounce would still cost one request per drag, and the point is that N people on N scratchpads
 * must not multiply into N × gestures of traffic.
 *
 * Three properties, each of which someone eventually depends on:
 *
 * * a burst of edits produces **one** request, after the burst;
 * * a save already in flight does not race a second — the next runs after it returns, so the
 *   version the second carries is the one the first was answered with;
 * * `flush` writes immediately, for blur and navigation, because "your work is saved when you stop
 *   touching it" must not have an exception for closing the tab.
 */

export interface DebouncedSave {
  /** Note that something changed. Schedules a save; repeated calls collapse into one. */
  readonly schedule: () => void
  /** Save now if anything is pending — on blur, on navigate, on explicit save. */
  readonly flush: () => Promise<void>
  readonly saving: Ref<boolean>
  readonly saveError: Ref<string | null>
  /** How many requests this instance has issued. Read by the test that holds the rate down. */
  readonly writeCount: Ref<number>
}

export function useDebouncedScratchpadSave(
  save: () => Promise<void>,
  delayMs: number = SAVE_DEBOUNCE_MS,
): DebouncedSave {
  const saving = ref(false)
  const saveError = ref<string | null>(null)
  const writeCount = ref(0)
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending = false
  let inFlight: Promise<void> | null = null

  const clearTimer = (): void => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const run = async (): Promise<void> => {
    // Serialised rather than concurrent: two saves in flight would carry the same version, and the
    // second would be refused as stale — turning a fast typist into a conflict dialog.
    if (inFlight) {
      await inFlight
      if (!pending) return
    }
    if (!pending) return
    pending = false
    saving.value = true
    writeCount.value += 1
    const attempt = save()
      .then(() => { saveError.value = null })
      .catch((error: unknown) => { saveError.value = error instanceof Error ? error.message : String(error) })
      .finally(() => { saving.value = false; inFlight = null })
    inFlight = attempt
    await attempt
    // An edit that arrived while this one was in flight still has to reach the server.
    if (pending) await run()
  }

  const schedule = (): void => {
    pending = true
    clearTimer()
    timer = setTimeout(() => { timer = null; void run() }, delayMs)
  }

  const flush = async (): Promise<void> => {
    clearTimer()
    if (!pending && !inFlight) return
    await run()
  }

  // A component torn down mid-debounce would otherwise drop the edit silently.
  onScopeDispose(() => { clearTimer() })

  return { schedule, flush, saving, saveError, writeCount }
}
