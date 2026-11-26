// @vitest-environment jsdom
/**
 * A canvas's overlays open where the browser paints them: inside the element that has the screen, else in
 * the body. jsdom has no Fullscreen API, so `fullscreenElement` and its event are stubbed; that the overlay is
 * then visible is the browser suite's to show.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent } from 'vue'
import { useOverlayHost } from '../useOverlayHost'

const define = (value: Element | null) =>
  Object.defineProperty(window.document, 'fullscreenElement', { value, configurable: true, writable: true })

const mounted = () => {
  let host!: ReturnType<typeof useOverlayHost>
  const app = createApp(defineComponent({ setup() { host = useOverlayHost(); return () => null } }))
  app.mount(window.document.createElement('div'))
  return { host, unmount: () => app.unmount() }
}

afterEach(() => { define(null) })

describe('useOverlayHost', () => {
  it('opens in the body while nothing has the screen', () => {
    define(null)
    expect(mounted().host.value).toBe('body')
  })

  it('follows the element that takes the screen, and returns to the body when it leaves', () => {
    const { host, unmount } = mounted()
    const canvas = window.document.createElement('div')
    define(canvas)
    window.document.dispatchEvent(new Event('fullscreenchange'))
    expect(host.value).toBe(canvas)
    define(null)
    window.document.dispatchEvent(new Event('fullscreenchange'))
    expect(host.value).toBe('body')
    unmount()
  })

  it('stops following once its owner is gone', () => {
    const { host, unmount } = mounted()
    unmount()
    define(window.document.createElement('div'))
    window.document.dispatchEvent(new Event('fullscreenchange'))
    expect(host.value).toBe('body')
  })
})
