// @vitest-environment jsdom
//
// The sidebar opens no wider than a drag could ever make it.
//
// A drag is bounded at 45% of the grid; the initial width was not. A host asking for more than the
// bound opened that wide, and the first drag snapped the sidebar to the bound with no way back to
// where it had started. Mounted for real, because the clamp reads the grid's measured width.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, ref, type App, type Ref } from 'vue'
import { useSidebarResize } from './useSidebarResize'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; vi.restoreAllMocks() })

const mountedWith = (gridWidth: number, initialWidth: number): Ref<number> => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { width: gridWidth, left: 0, right: gridWidth, top: 0, bottom: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) },
  )
  let width: Ref<number> = ref(0)
  const Host = defineComponent({
    setup() {
      const gridRef = ref<HTMLElement | null>(null)
      width = useSidebarResize(gridRef, { initialWidth, minWidth: 380, maxWidth: 760 }).sidebarWidth
      return () => h('div', { ref: gridRef })
    },
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp(Host)
  app.mount(host)
  return width
}

describe('the initial sidebar width', () => {
  it('is brought down to the widest a drag could reach', () => {
    // 45% of 1150 is 517: what a drag is bounded at on this grid.
    expect(mountedWith(1150, 660).value).toBe(517)
  })

  it('is kept when it already lies within the bound', () => {
    expect(mountedWith(1150, 480).value).toBe(480)
  })

  it('is left alone on a grid too narrow to drag, where the layout has stacked', () => {
    expect(mountedWith(700, 660).value).toBe(660)
  })
})

const mountedOnTheLeft = (gridWidth: number): ReturnType<typeof useSidebarResize> => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { width: gridWidth, left: 100, right: 100 + gridWidth, top: 0, bottom: 0, height: 0, x: 100, y: 0,
      toJSON: () => ({}) },
  )
  const held: { resize?: ReturnType<typeof useSidebarResize> } = {}
  const Host = defineComponent({
    setup() {
      const gridRef = ref<HTMLElement | null>(null)
      held.resize = useSidebarResize(gridRef, {
        initialWidth: 500, minWidth: 440, maxWidth: 900, edge: 'left', maxShare: 0.6,
      })
      return () => h('div', { ref: gridRef })
    },
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp(Host)
  app.mount(host)
  if (!held.resize) throw new Error('not mounted')
  return held.resize
}

describe('a panel on the left edge', () => {
  it('is as wide as the drag is from the left edge, within its share of the grid', () => {
    const resize = mountedOnTheLeft(1200)
    resize.startResize(new MouseEvent('mousedown'))
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 100 + 650 }))
    expect(resize.sidebarWidth.value).toBe(650)
    // 60% of 1200 is 720: the farthest a drag reaches.
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 100 + 1100 }))
    expect(resize.sidebarWidth.value).toBe(720)
    window.dispatchEvent(new MouseEvent('mouseup'))
  })

  it('grows with → and shrinks with ←, never below its least width', () => {
    const resize = mountedOnTheLeft(1200)
    resize.nudge(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    expect(resize.sidebarWidth.value).toBe(524)
    for (let step = 0; step < 10; step += 1) resize.nudge(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    expect(resize.sidebarWidth.value).toBe(440)
  })
})
