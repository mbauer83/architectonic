/**
 * A derived-graph request survives past the default budget through the dev proxy.
 *
 * The failure this guards: a long operation — a rendered GSN case, a viewpoint execution, a
 * neighbourhood traversal — is severed by the *proxy* at the generic 10s+headroom while the client
 * is still happily waiting on its own 60s budget. The user sees a network error from a request that
 * was going to succeed, and nothing in either program's logs says the proxy did it. Two independent
 * budgets is the bug; the shared classification is the fix; this is the proof the proxy honours it.
 *
 * Run through a real Vite dev server built from the shipped `vite.config.ts`, so the proxy is the
 * one that ships. Only each context's `target` is rewritten, to a stub that stalls — the upstream is
 * not what is under test, and every timeout still comes from the config rather than being recomputed
 * here. A test that derived the budgets again would agree with itself and prove nothing.
 *
 * One real 12-second wait, deliberately. The asymmetry is a claim about seconds; a millisecond
 * simulation of it would assert only the arithmetic that the two assertions above already cover.
 */
import { createServer as createHttpServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import {
  createServer as createViteServer,
  loadConfigFromFile,
  type ProxyOptions,
  type ViteDevServer,
} from 'vite'

/** Longer than the default budget + headroom (15s), well inside the derived-graph one (65s). */
const UPSTREAM_DELAY_MS = 12_000

const projectRoot = new URL('../../..', import.meta.url).pathname

/**
 * The shipped `vite.config.ts`, loaded the way Vite loads it.
 *
 * Not a static import: the config belongs to the `tsconfig.node.json` program and this test to the
 * app program, and importing across them is the TS6305 that already forced the timeout policy to be
 * generated as JSON. Loading through Vite's own resolver reads the file that actually ships.
 */
let cachedProxy: Record<string, ProxyOptions> | null = null

const shippedProxy = async (): Promise<Record<string, ProxyOptions>> => {
  if (cachedProxy) return cachedProxy
  const loaded = await loadConfigFromFile({ command: 'serve', mode: 'development' })
  const proxy = loaded?.config.server?.proxy as Record<string, ProxyOptions> | undefined
  if (!proxy) throw new Error('vite.config no longer declares server.proxy')
  cachedProxy = proxy
  return proxy
}

/** The entry whose context matches `path`, in declaration order — which is what Vite itself does. */
const entryFor = async (path: string): Promise<[string, ProxyOptions]> => {
  for (const [context, entry] of Object.entries(await shippedProxy())) {
    const matches = context.startsWith('^')
      ? new RegExp(context).test(path)
      : path.startsWith(context)
    if (matches) return [context, entry]
  }
  throw new Error(`no proxy context matches ${path}`)
}

let upstream: Server
let vite: ViteDevServer
let baseUrl: string

beforeAll(async () => {
  upstream = createHttpServer((_req, res) => {
    setTimeout(() => {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ slow: true }))
    }, UPSTREAM_DELAY_MS)
  })
  await new Promise<void>((resolve) => upstream.listen(0, '127.0.0.1', resolve))
  const upstreamUrl = `http://127.0.0.1:${(upstream.address() as AddressInfo).port}`

  // The shipped contexts and timeouts, pointed at the stall. Nothing else is changed.
  const proxy = Object.fromEntries(
    Object.entries(await shippedProxy()).map(([context, entry]) => [
      context,
      { ...entry, target: upstreamUrl, configure: undefined },
    ]),
  )
  vite = await createViteServer({
    configFile: false,
    root: projectRoot,
    logLevel: 'silent',
    server: { proxy, port: 0, strictPort: false },
  })
  await vite.listen()
  const address = vite.httpServer?.address() as AddressInfo
  baseUrl = `http://127.0.0.1:${address.port}`
}, 60_000)

afterAll(async () => {
  await vite?.close()
  await new Promise<void>((resolve) => upstream.close(() => resolve()))
})

describe('the dev proxy and the client agree on a long operation', () => {
  const derivedGraphPath = '/api/assurance/nodes/HAZ@1/neighbors'
  const defaultPath = '/api/entities'

  it('classifies a derived-graph route into its own context, not the generic one', async () => {
    const [context, entry] = await entryFor(derivedGraphPath)

    expect(context).not.toBe('/api')
    // 60s budget + 5s headroom: the proxy waits longer than the client, so a timeout is always the
    // client's own decision rather than a severed connection it cannot explain.
    expect(entry.timeout).toBe(65_000)
    expect(entry.proxyTimeout).toBe(65_000)
  })

  it('gives an ordinary read the generic budget, which is shorter', async () => {
    const [context, entry] = await entryFor(defaultPath)

    expect(context).toBe('/api')
    expect(entry.timeout).toBe(15_000)
    const [, derived] = await entryFor(derivedGraphPath)
    expect(entry.timeout!).toBeLessThan(derived.timeout!)
  })

  it('lets a 12-second derived-graph response through', async () => {
    const response = await fetch(`${baseUrl}${derivedGraphPath}`)

    expect(
      response.status,
      'the proxy severed a request the client was still waiting for',
    ).toBe(200)
  }, 40_000)
})
