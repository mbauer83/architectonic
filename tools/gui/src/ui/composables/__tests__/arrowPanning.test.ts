// @vitest-environment jsdom
//
// On a viewer whose elements the keyboard does not walk (a viewpoint's view, an assurance projection), the
// arrows move the window: a fifth of it, or a whole window with Shift (D13, L10).

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, ref, type App } from 'vue'
import { useArrowPanning } from '../useArrowPanning'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null })

const mounted = () => {
  const host = document.createElement('div')
  const panBy = vi.fn()
  app = createApp(defineComponent({ setup() { useArrowPanning(ref(host), panBy); return () => null } }))
  app.mount(document.createElement('div'))
  return { host, panBy }
}
const press = (target: HTMLElement, key: string, init: KeyboardEventInit = {}) => {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  target.dispatchEvent(event)
  return event
}

describe('the arrows on a diagram window', () => {
  it('move the window a fifth of itself, and a whole window with Shift', () => {
    const { host, panBy } = mounted()
    expect(press(host, 'ArrowRight').defaultPrevented).toBe(true)
    press(host, 'ArrowUp', { shiftKey: true })
    expect(panBy.mock.calls).toEqual([[0.2, 0], [0, -1]])
  })

  it('leave a field typed into, a modified key and any other key alone', () => {
    const { host, panBy } = mounted()
    const field = document.createElement('input')
    host.appendChild(field)
    press(field, 'ArrowLeft')
    press(host, 'ArrowLeft', { ctrlKey: true })
    press(host, 'a')
    expect(panBy).not.toHaveBeenCalled()
  })
})
