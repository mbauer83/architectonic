// @vitest-environment jsdom
//
// A reader who asked for less motion gets every graph layout's result at once (B94).
//
// The layouts already landed at once where there is no frame clock — "the resting arrangement is the
// contract and the motion is presentation". A browser always has a frame clock, so that branch never ran
// for a real reader, and the force cooling and the eased cluster move played regardless of
// `prefers-reduced-motion`. These run with a frame clock present and the preference set.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent } from 'vue'
import { useForceGraph } from '../useForceGraph'

const prefersReducedMotion = (reduce: boolean) => {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduce && query.includes('prefers-reduced-motion: reduce'),
    media: query, addEventListener: () => {}, removeEventListener: () => {},
  }))
}

const graph = () => {
  let api!: ReturnType<typeof useForceGraph>
  createApp(defineComponent({
    setup() {
      api = useForceGraph(() => 800, () => 600)
      for (const id of ['APP1', 'APP2', 'MOT1', 'MOT2']) api.addNode({ id, label: id, type: id.slice(0, 3) })
      return () => null
    },
  })).mount(document.createElement('div'))
  return api
}

let frames: ReturnType<typeof vi.fn>
beforeEach(() => {
  frames = vi.fn(() => 1)
  vi.stubGlobal('requestAnimationFrame', frames)
  vi.stubGlobal('cancelAnimationFrame', () => {})
})
afterEach(() => { vi.unstubAllGlobals() })

describe('with reduced motion requested', () => {
  it('moves a cluster layout straight to its arrangement, with no frames', () => {
    prefersReducedMotion(true)
    const api = graph()
    const settled = vi.fn()

    api.applyGroupClusterLayout((id) => id.slice(0, 3), undefined, undefined, { onSettled: settled })

    expect(frames).not.toHaveBeenCalled()
    expect(settled).toHaveBeenCalledOnce()
  })

  it('cools the force layout to rest synchronously', () => {
    prefersReducedMotion(true)
    const api = graph()

    api.animateForceLayout()

    expect(frames).not.toHaveBeenCalled()
  })
})

describe('without the preference', () => {
  it('still animates, frame by frame', () => {
    prefersReducedMotion(false)
    const api = graph()

    api.animateForceLayout()

    expect(frames).toHaveBeenCalled()
  })
})
