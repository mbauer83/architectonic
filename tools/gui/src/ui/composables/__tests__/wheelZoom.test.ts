// @vitest-environment jsdom
/**
 * Cursor-anchored zoom, which is the part of a viewport that is wrong in a way nobody can name:
 * the picture grows, but not around where you were pointing, so reading a dense diagram becomes a
 * chase. The anchoring is one line of arithmetic shared by both diagram viewports, so it is pinned
 * by its defining property rather than by the numbers it happens to produce.
 */

import { describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, nextTick, ref } from 'vue'
import { useWheelZoom, type ViewTransform } from '../useWheelZoom'

const VIEWPORT_LEFT = 40
const VIEWPORT_TOP = 25

const harness = () => {
  const container = window.document.createElement('div')
  container.getBoundingClientRect = () =>
    ({ left: VIEWPORT_LEFT, top: VIEWPORT_TOP, width: 800, height: 600 }) as DOMRect
  const view: ViewTransform = { scale: ref(1), tx: ref(0), ty: ref(0) }

  const app = createApp(defineComponent({
    setup() {
      useWheelZoom(ref(container), view)
      return () => null
    },
  }))
  app.mount(window.document.createElement('div'))
  return { container, view, unmount: () => app.unmount() }
}

const wheel = (container: HTMLElement, deltaY: number, clientX = 240, clientY = 175) => {
  const event = new WheelEvent('wheel', { deltaY, clientX, clientY, cancelable: true })
  container.dispatchEvent(event)
  return event
}

/** Where a point of the viewport lands in the content, under the current transform. */
const contentPointUnder = ({ scale, tx, ty }: ViewTransform, clientX: number, clientY: number) => ({
  x: (clientX - VIEWPORT_LEFT - tx.value) / scale.value,
  y: (clientY - VIEWPORT_TOP - ty.value) / scale.value,
})

describe('zooming with the wheel', () => {
  it('keeps what was under the cursor under the cursor', () => {
    const { container, view } = harness()
    const before = contentPointUnder(view, 300, 200)

    wheel(container, -100, 300, 200)

    const after = contentPointUnder(view, 300, 200)
    expect(view.scale.value).toBeGreaterThan(1)
    expect(after.x).toBeCloseTo(before.x, 6)
    expect(after.y).toBeCloseTo(before.y, 6)
  })

  it('holds the anchor across a run of notches, not just the first', () => {
    const { container, view } = harness()
    const before = contentPointUnder(view, 500, 400)

    for (let notch = 0; notch < 6; notch += 1) wheel(container, -100, 500, 400)

    const after = contentPointUnder(view, 500, 400)
    expect(after.x).toBeCloseTo(before.x, 6)
    expect(after.y).toBeCloseTo(before.y, 6)
  })

  it('zooms out on the other direction', () => {
    const { container, view } = harness()

    wheel(container, 100)

    expect(view.scale.value).toBeLessThan(1)
  })

  it('stops the page scrolling underneath it', () => {
    const { container } = harness()

    expect(wheel(container, -100).defaultPrevented).toBe(true)
  })
})

describe('the range the scale may not leave', () => {
  it('will not magnify past the ceiling', () => {
    const { container, view } = harness()

    for (let notch = 0; notch < 60; notch += 1) wheel(container, -100)

    expect(view.scale.value).toBe(8)
  })

  it('will not shrink past the floor', () => {
    const { container, view } = harness()

    for (let notch = 0; notch < 60; notch += 1) wheel(container, 100)

    expect(view.scale.value).toBe(0.2)
  })
})

describe('after the viewport goes away', () => {
  it('stops zooming anything', () => {
    const { container, view, unmount } = harness()

    unmount()
    wheel(container, -100)

    expect(view.scale.value).toBe(1)
  })
})

describe('a viewport that is not mounted yet', () => {
  it('is left alone rather than measured', () => {
    const view: ViewTransform = { scale: ref(1), tx: ref(0), ty: ref(0) }
    const app = createApp(defineComponent({
      setup() {
        useWheelZoom(ref(null), view)
        return () => null
      },
    }))
    app.mount(window.document.createElement('div'))

    expect(() => window.dispatchEvent(new WheelEvent('wheel', { deltaY: -100 }))).not.toThrow()
    expect(view.scale.value).toBe(1)
    app.unmount()
  })
})

describe('a viewport element that is swapped out', () => {
  it('lets go of the one it left', async () => {
    const first = window.document.createElement('div')
    first.getBoundingClientRect = () => ({ left: 0, top: 0, width: 10, height: 10 }) as DOMRect
    const elementRef = ref<HTMLElement | null>(first)
    const view: ViewTransform = { scale: ref(1), tx: ref(0), ty: ref(0) }
    const app = createApp(defineComponent({
      setup() {
        useWheelZoom(elementRef, view)
        return () => null
      },
    }))
    app.mount(window.document.createElement('div'))

    elementRef.value = null
    await nextTick()
    first.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, cancelable: true }))

    expect(view.scale.value).toBe(1)
    app.unmount()
  })
})

describe('the handler', () => {
  it('is registered non-passively, since it must be able to cancel the scroll', () => {
    const container = window.document.createElement('div')
    const addEventListener = vi.spyOn(container, 'addEventListener')
    const app = createApp(defineComponent({
      setup() {
        useWheelZoom(ref(container), { scale: ref(1), tx: ref(0), ty: ref(0) })
        return () => null
      },
    }))
    app.mount(window.document.createElement('div'))

    expect(addEventListener).toHaveBeenCalledWith('wheel', expect.any(Function), { passive: false })
    app.unmount()
  })
})
