// @vitest-environment jsdom
//
// The gesture hint under a viewport is bounded by the window it sits in: a hint longer than the window wraps,
// so every word is on screen and nothing is left to a tooltip. (That it wraps inside the window is layout,
// asserted in the browser: `text-stays-whole.spec.ts`.)

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { createApp, h, type App } from 'vue'
import DiagramViewportControls from '../DiagramViewportControls.vue'

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
})

let app: App | null = null
afterEach(() => { app?.unmount(); app = null })

const HINT = 'Drag an element, or a box by its title, to move it · drag on paper to select · Shift-click adds'

const hintOf = (isFullscreen: boolean): HTMLElement => {
  const host = document.createElement('div')
  app = createApp({
    render: () => h('div', [h(DiagramViewportControls, {
      isTransformed: false, isFullscreen, canFullscreen: false, hint: HINT,
    })]),
  })
  app.mount(host)
  return host.querySelector<HTMLElement>('[data-testid="viewport-hint"]')!
}

describe('the viewport hint', () => {
  it('shows its whole text, with nothing left to a tooltip', () => {
    const hint = hintOf(false)
    expect(hint.textContent?.trim()).toBe(HINT)
    expect(hint.title).toBe('')
  })

  it('says how to leave fullscreen', () => {
    expect(hintOf(true).textContent?.trim()).toBe(`${HINT} · Esc to exit`)
  })
})
