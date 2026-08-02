import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Every request an adapter makes builds its URL through `buildUrl`.
 *
 * Five sync call sites passed the path as a bare string — `fetchJson('/api/sync/status', …)` — which
 * works in a browser, because a relative URL resolves against the document, and nowhere else. It is
 * also a second spelling of the `/api` prefix that `buildUrl` owns along with the `/admin/api`
 * decision, so a change to either would have had to find these by hand.
 *
 * It surfaced the moment the conformance harness ran the same adapter under Node, where a relative
 * URL has nothing to resolve against: `TypeError: Failed to parse URL from /api/sync/status`. The
 * harness cannot keep catching it, though — it only walks *reads*, and four of the five were writes.
 * So this is the guard, and it is deliberately a source scan rather than a behavioural test: what is
 * being forbidden is a spelling.
 */

const ADAPTER_DIR = join(import.meta.dirname, '.')

/** A path literal beginning with the API prefix, wherever it appears in a call. */
const API_PREFIX_LITERAL = /['"`]\/(api|admin\/api)\//

/**
 * `diagramImageUrl` is the one legitimate absolute-path literal: it is not a request. It returns a
 * string for an `<img src>`, which a browser resolves itself, and putting it through `buildUrl` would
 * hand the element an absolute URL carrying the current origin for no reason.
 */
const PERMITTED = new Set(['diagramImageUrl'])

const adapterSources = (): readonly { name: string; text: string }[] =>
  readdirSync(ADAPTER_DIR)
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts'))
    .map((name) => ({ name, text: readFileSync(join(ADAPTER_DIR, name), 'utf8') }))

describe('adapter URL construction', () => {
  it('reads the adapter sources it means to scan', () => {
    const names = adapterSources().map((s) => s.name)
    expect(names).toContain('HttpModelRepository.ts')
    expect(names).toContain('httpTransport.ts')
  })

  it('routes every request through buildUrl rather than a bare path literal', () => {
    const offenders = adapterSources().flatMap(({ name, text }) =>
      text
        .split('\n')
        .map((line, index) => ({ line, at: `${name}:${index + 1}` }))
        .filter(({ line }) => API_PREFIX_LITERAL.test(line))
        .filter(({ line }) => ![...PERMITTED].some((permitted) => line.includes(permitted)))
        // A comment or a doc block may quote a path; only code is being constrained.
        .filter(({ line }) => !/^\s*(\/\/|\*|\/\*)/.test(line))
        .map(({ at, line }) => `${at}: ${line.trim()}`),
    )
    expect(
      offenders,
      'these build a URL from a bare `/api/…` literal. Use `buildUrl(\'/…\')`, which owns the '
        + 'prefix and the admin-tier decision — and which resolves outside a browser, where a '
        + 'relative URL has no document to resolve against.',
    ).toEqual([])
  })
})
