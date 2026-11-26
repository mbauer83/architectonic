// @vitest-environment jsdom
//
// The gesture hint under a viewport is bounded by the window it sits in: a hint longer than the window ends
// in … rather than running off both edges, and the whole of it is there on hover.

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, type App } from 'vue'
import DiagramViewportControls from '../DiagramViewportControls.vue'

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
  it('carries its whole text on hover, for when the window cuts it short', () => {
    const hint = hintOf(false)
    expect(hint.textContent?.trim()).toBe(HINT)
    expect(hint.title).toBe(HINT)
  })

  it('says how to leave fullscreen, on hover too', () => {
    expect(hintOf(true).title).toBe(`${HINT} · Esc to exit`)
  })
})
