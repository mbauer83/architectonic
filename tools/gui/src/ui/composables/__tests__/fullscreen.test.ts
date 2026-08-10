// @vitest-environment jsdom
/**
 * jsdom implements none of the Fullscreen API, so every part of it is stubbed here. That makes
 * these tests about the composable's own decisions — which of request/exit to call, and what it
 * concludes from a `fullscreenchange` — rather than about fullscreen actually happening, which is
 * the browser suite's job.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, ref } from 'vue'
import { useFullscreen } from '../useFullscreen'

const define = (property: string, value: unknown) =>
  Object.defineProperty(window.document, property, { value, configurable: true, writable: true })

const mounted = <T>(setup: () => T): { value: T; unmount: () => void } => {
  let value!: T
  const app = createApp(defineComponent({ setup() { value = setup(); return () => null } }))
  app.mount(window.document.createElement('div'))
  return { value, unmount: () => app.unmount() }
}

const harness = (
  { enabled = true, current = null as Element | null, request = vi.fn().mockResolvedValue(undefined) } = {},
) => {
  const element = window.document.createElement('div')
  Object.defineProperty(element, 'requestFullscreen', { value: request, configurable: true })
  const exit = vi.fn().mockResolvedValue(undefined)
  define('fullscreenEnabled', enabled)
  define('fullscreenElement', current)
  define('exitFullscreen', exit)
  const { value, unmount } = mounted(() => useFullscreen(ref(element)))
  return { ...value, element, request, exit, unmount }
}

afterEach(() => {
  define('fullscreenElement', null)
})

describe('the control', () => {
  it('asks for fullscreen on the element it was given', async () => {
    const { toggle, request } = harness()

    await toggle()

    expect(request).toHaveBeenCalledOnce()
  })

  it('leaves fullscreen when something is already in it', async () => {
    const element = window.document.createElement('div')
    const { toggle, exit, request } = harness({ current: element })

    await toggle()

    expect(exit).toHaveBeenCalledOnce()
    expect(request).not.toHaveBeenCalled()
  })

  it('is absent, not dead, where the document forbids fullscreen', async () => {
    const { isSupported, toggle, request } = harness({ enabled: false })

    await toggle()

    expect(isSupported).toBe(false)
    expect(request).not.toHaveBeenCalled()
  })

  it('does not raise when the browser refuses the request', async () => {
    const refused = vi.fn().mockRejectedValue(new Error('permissions policy'))
    const { toggle } = harness({ request: refused })

    await expect(toggle()).resolves.toBeUndefined()
  })
})

describe('what the page believes about its own state', () => {
  it('follows the document rather than the button, so Esc is noticed too', () => {
    const { isFullscreen, element } = harness()
    expect(isFullscreen.value).toBe(false)

    define('fullscreenElement', element)
    window.document.dispatchEvent(new Event('fullscreenchange'))
    expect(isFullscreen.value).toBe(true)

    define('fullscreenElement', null)
    window.document.dispatchEvent(new Event('fullscreenchange'))
    expect(isFullscreen.value).toBe(false)
  })

  it('stays false when some other element is the one in fullscreen', () => {
    const { isFullscreen } = harness()

    define('fullscreenElement', window.document.createElement('section'))
    window.document.dispatchEvent(new Event('fullscreenchange'))

    expect(isFullscreen.value).toBe(false)
  })

  it('stops listening once the view is gone', () => {
    const { isFullscreen, element, unmount } = harness()

    unmount()
    define('fullscreenElement', element)
    window.document.dispatchEvent(new Event('fullscreenchange'))

    expect(isFullscreen.value).toBe(false)
  })
})
