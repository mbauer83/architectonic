/**
 * The canvas writes at most once a second per open scratchpad, and never once per gesture.
 *
 * This is the assertion behind the design decision, not a performance nicety. A drag emits a
 * position stream; the repository behind the endpoint is a git working tree behind a mutation gate
 * and a write queue, and many small writes is precisely the traffic shape the previous release was
 * spent recovering from. "The canvas got chatty" is not something anyone notices until git-sync
 * starts thrashing, so it is measured here.
 */

import { describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useDebouncedScratchpadSave } from '../useDebouncedScratchpadSave'

/** Runs the composable inside a scope, so `onScopeDispose` has one to attach to. */
const inScope = <T>(build: () => T): { value: T; stop: () => void } => {
  const scope = effectScope()
  const value = scope.run(build) as T
  return { value, stop: () => scope.stop() }
}

describe('the canvas save rate', () => {
  it('turns a burst of edits into exactly one write', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => {})
    const { value: debounced, stop } = inScope(() => useDebouncedScratchpadSave(save, 1000))

    // A drag across the canvas: sixty positions, the shape a per-gesture write would send whole.
    for (let i = 0; i < 60; i++) debounced.schedule()
    await vi.advanceTimersByTimeAsync(1000)

    expect(save).toHaveBeenCalledTimes(1)
    expect(debounced.writeCount.value).toBe(1)
    stop()
    vi.useRealTimers()
  })

  it('holds to one write per second under continuous editing', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => {})
    const { value: debounced, stop } = inScope(() => useDebouncedScratchpadSave(save, 1000))

    // Ten seconds of unbroken editing at 20 edits a second — 200 gestures.
    for (let tick = 0; tick < 200; tick++) {
      debounced.schedule()
      await vi.advanceTimersByTimeAsync(50)
    }
    await vi.advanceTimersByTimeAsync(1000)

    // The endpoint sees a save, never a drag: at most one per second of elapsed time.
    expect(debounced.writeCount.value).toBeLessThanOrEqual(10)
    expect(save.mock.calls.length).toBeLessThanOrEqual(10)
    stop()
    vi.useRealTimers()
  })

  it('does not write at all when nothing changed', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => {})
    const { value: debounced, stop } = inScope(() => useDebouncedScratchpadSave(save, 1000))

    await vi.advanceTimersByTimeAsync(5000)
    await debounced.flush()

    expect(save).not.toHaveBeenCalled()
    stop()
    vi.useRealTimers()
  })

  it('flushes immediately on blur or navigate, without waiting out the idle period', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => {})
    const { value: debounced, stop } = inScope(() => useDebouncedScratchpadSave(save, 1000))

    debounced.schedule()
    await debounced.flush()

    expect(save).toHaveBeenCalledTimes(1)
    stop()
    vi.useRealTimers()
  })

  it('never runs two saves at once, so the second cannot carry a stale version', async () => {
    vi.useFakeTimers()
    let concurrent = 0
    let maxConcurrent = 0
    const save = vi.fn(async () => {
      concurrent += 1
      maxConcurrent = Math.max(maxConcurrent, concurrent)
      await new Promise((resolve) => setTimeout(resolve, 500))
      concurrent -= 1
    })
    const { value: debounced, stop } = inScope(() => useDebouncedScratchpadSave(save, 100))

    debounced.schedule()
    await vi.advanceTimersByTimeAsync(100)
    debounced.schedule()
    await vi.advanceTimersByTimeAsync(100)
    await vi.advanceTimersByTimeAsync(1000)

    expect(maxConcurrent).toBe(1)
    stop()
    vi.useRealTimers()
  })

  it('reports a failed save rather than swallowing it', async () => {
    vi.useFakeTimers()
    // A rejected promise rather than an `async` body that only throws: it is what a 409 actually
    // produces, and it does not claim to await anything.
    const save = vi.fn(() => Promise.reject(new Error('has moved on: reload')))
    const { value: debounced, stop } = inScope(() => useDebouncedScratchpadSave(save, 100))

    debounced.schedule()
    await vi.advanceTimersByTimeAsync(100)

    expect(debounced.saveError.value).toContain('has moved on')
    stop()
    vi.useRealTimers()
  })

  it('still writes an edit that arrived while a save was in flight', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => { await new Promise((resolve) => setTimeout(resolve, 300)) })
    const { value: debounced, stop } = inScope(() => useDebouncedScratchpadSave(save, 100))

    debounced.schedule()
    await vi.advanceTimersByTimeAsync(100)
    // Mid-flight edit: dropping it is how a canvas loses the last thing someone typed.
    debounced.schedule()
    await vi.advanceTimersByTimeAsync(2000)

    expect(save.mock.calls.length).toBeGreaterThanOrEqual(2)
    stop()
    vi.useRealTimers()
  })
})
