import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { usePanCanvasStyle } from '../usePanCanvasStyle'

/**
 * `will-change: transform` must not be held while the canvas is standing still.
 *
 * Both diagram viewports declared it permanently, which is the documented anti-pattern: the property
 * warns the browser *just before* a change, and a permanent declaration instead keeps the element on
 * its own compositing layer for the life of the page. It surfaced as a rendering fault, not as
 * slowness — a diagram's labels missing until the pointer moved over it. The glyphs were in the DOM,
 * visible, opaque and correctly sized; their layer had not been rasterised with them.
 *
 * So the assertions are: absent at rest, present while moving, and gone again once the view settles.
 */
const withScope = <T,>(build: () => T): T => {
  const scope = effectScope()
  const value = scope.run(build)!
  return value
}

describe('the pan canvas style', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('does not declare will-change at rest', () => {
    const { canvasStyle } = withScope(() => usePanCanvasStyle(ref(1), ref(0), ref(0)))

    expect(canvasStyle.value.willChange).toBeUndefined()
  })

  it('still declares the transform at rest', () => {
    // The hint is what comes and goes; the transform is the whole point of the style.
    const { canvasStyle } = withScope(() => usePanCanvasStyle(ref(0.5), ref(12), ref(-4)))

    expect(canvasStyle.value.transform).toBe('translate(12px, -4px) scale(0.5)')
    expect(canvasStyle.value.transformOrigin).toBe('0 0')
  })

  it('declares will-change as soon as the canvas moves', async () => {
    const tx = ref(0)
    const style = withScope(() => usePanCanvasStyle(ref(1), tx, ref(0)))

    tx.value = 40
    await nextTick()

    expect(style.canvasStyle.value.willChange).toBe('transform')
  })

  it('drops it again once the view has settled', async () => {
    const scale = ref(1)
    const style = withScope(() => usePanCanvasStyle(scale, ref(0), ref(0)))

    scale.value = 1.4
    await nextTick()
    vi.advanceTimersByTime(1000)
    await nextTick()

    expect(style.canvasStyle.value.willChange).toBeUndefined()
  })

  it('keeps it across the gaps within one gesture', async () => {
    // A wheel zoom arrives as a stream of events with pauses between them. Dropping the hint in a
    // pause and re-adding it would create and destroy a layer under a reader mid-gesture.
    const scale = ref(1)
    const style = withScope(() => usePanCanvasStyle(scale, ref(0), ref(0)))

    scale.value = 1.1
    await nextTick()
    vi.advanceTimersByTime(120)
    scale.value = 1.2
    await nextTick()
    vi.advanceTimersByTime(300)

    expect(style.canvasStyle.value.willChange).toBe('transform')
  })
})
