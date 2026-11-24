// @vitest-environment jsdom
//
// Finding an element (Q21) moves the window to it at a size it reads at, and the window's own
// readings — where a picture point is on screen, which part of the picture is shown — agree with it.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, ref } from 'vue'
import { useFittedPanZoom } from '../useFittedPanZoom'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

const mount = () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  // No frame clock: the glide lands at once, as it does under reduced motion.
  vi.stubGlobal('requestAnimationFrame', undefined)
  const container = document.createElement('div')
  vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({ width: 800, height: 600 } as DOMRect)
  const wrapper = document.createElement('div')
  wrapper.innerHTML = '<svg viewBox="0 0 20000 2000"></svg>'
  let api!: ReturnType<typeof useFittedPanZoom>
  createApp(defineComponent({
    setup() { api = useFittedPanZoom(ref(container), ref(wrapper)); return () => null },
  })).mount(document.createElement('div'))
  return api
}

describe('going to a part of the picture', () => {
  it('centres it in the window at a readable size when the window was far out', () => {
    const api = mount()
    api.scale.value = 0.04
    api.goTo({ left: 15000, top: 1000, right: 15200, bottom: 1060 })
    expect(api.scale.value).toBeCloseTo(0.7)
    expect(api.toWindow({ x: 15100, y: 1030 })).toEqual({ x: 400, y: 300 })
  })

  it('keeps a closer zoom, and steps back only as far as a large part needs to fit', () => {
    const api = mount()
    api.scale.value = 2
    api.goTo({ left: 0, top: 0, right: 100, bottom: 50 })
    expect(api.scale.value).toBe(2)
    api.goTo({ left: 0, top: 0, right: 7200, bottom: 400 })
    expect(api.scale.value).toBeCloseTo(0.1)
  })

  it('reads the window as the part of the picture it shows', () => {
    const api = mount()
    api.showView({ x: 1000, y: 500, percent: 50 })
    expect(api.windowExtent(800, 600)).toEqual({ left: 200, top: -100, right: 1800, bottom: 1100 })
  })
})
