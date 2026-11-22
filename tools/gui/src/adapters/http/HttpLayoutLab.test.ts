// @vitest-environment jsdom
/**
 * The lab's client: whether the backend serves the lab (which decides the menu entry), and its two
 * reads, with the backend's refusal sentence carried to the page rather than its envelope.
 *
 * A lab switched off answers 404 on its status route; a deployment whose SPA fallback answered the
 * path with its HTML shell would be a 200 that is not the lab, and must read as off too.
 */
import { Effect } from 'effect'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { labPicture, layoutLabIsOn } from './HttpLayoutLab'

const answering = (body: string, status = 200, type = 'application/json') =>
  vi.fn<typeof fetch>(async () => new Response(body, { status, headers: { 'Content-Type': type } }))

afterEach(() => vi.unstubAllGlobals())

describe('whether the lab is on, which decides the menu entry', () => {
  it('is on when the status route answers that it is', async () => {
    const fetch = answering('{"enabled": true}')
    vi.stubGlobal('fetch', fetch)
    expect(await layoutLabIsOn()).toBe(true)
    expect(String(fetch.mock.calls[0][0])).toMatch(/\/lab\/layout$/)
  })

  it('is off when the route is not served', async () => {
    vi.stubGlobal('fetch', answering('{"detail": "Not Found"}', 404))
    expect(await layoutLabIsOn()).toBe(false)
  })

  it('is off when something else answers the path, such as the application shell', async () => {
    vi.stubGlobal('fetch', answering('<html><main>app shell</main></html>', 200, 'text/html'))
    expect(await layoutLabIsOn()).toBe(false)
  })

  it('is off when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network down') }))
    expect(await layoutLabIsOn()).toBe(false)
  })
})

describe('the lab reads', () => {
  it('posts the layout and answers the composed picture', async () => {
    const fetch = answering('<svg/>', 200, 'image/svg+xml')
    vi.stubGlobal('fetch', fetch)
    const layout = { elements: { 'APP@1.a': { x: 1, y: 2 } } }
    expect(await Effect.runPromise(labPicture('ARC@1.a.test', layout))).toBe('<svg/>')
    const init = fetch.mock.calls[0][1]
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ layout })
  })

  it('carries a plain refusal sentence, and a body that is not an envelope as it is', async () => {
    vi.stubGlobal('fetch', answering('{"detail": "needs both x and y"}', 422))
    expect((await Effect.runPromise(Effect.flip(labPicture('ARC@1.a.test', {})))).message).toBe('needs both x and y')
    vi.stubGlobal('fetch', answering('upstream broke', 502, 'text/plain'))
    expect((await Effect.runPromise(Effect.flip(labPicture('ARC@1.a.test', {})))).message).toBe('upstream broke')
  })

})
