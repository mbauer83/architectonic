// @vitest-environment jsdom
/**
 * The canvas popover stays inside the window when a level grows within itself: the picker opening into
 * the create form made it taller than the room below the point, and its button lay off screen.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, ref, type App } from 'vue'
import { useCanvasPopover } from '../useCanvasPopover'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null; document.body.innerHTML = ''; vi.unstubAllGlobals() })

describe('the canvas popover', () => {
  it('is fitted into the window again when what it shows grows', async () => {
    const seen: { resized?: () => void; popover?: ReturnType<typeof useCanvasPopover> } = {}
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { seen.resized = callback }
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    vi.stubGlobal('innerHeight', 600)
    vi.stubGlobal('innerWidth', 1000)
    let height = 100
    const Host = defineComponent(() => {
      const host = ref<HTMLElement | null>(null)
      const pop = ref<HTMLElement | null>(null)
      const popover = useCanvasPopover(host, pop)
      seen.popover = popover
      return () => h('div', { ref: host }, popover.mode.value ? [h('div', {
        ref: pop,
        onVnodeMounted: (node) => {
          const element = node.el as HTMLElement
          element.getBoundingClientRect = () => ({ width: 300, height } as DOMRect)
        },
      })] : [])
    })
    const mount = document.createElement('div')
    document.body.appendChild(mount)
    app = createApp(Host)
    app.mount(mount)
    if (!seen.popover) throw new Error('not mounted')
    const { mode, position, at } = seen.popover
    position(100, 400)
    mode.value = 'create'
    await nextTick()
    await nextTick()
    expect(at.value.y).toBe(400)
    height = 300
    seen.resized?.()
    expect(at.value.y).toBe(600 - 300 - 8)
  })
})
