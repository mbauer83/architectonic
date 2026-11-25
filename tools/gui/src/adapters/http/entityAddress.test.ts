// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { entityAddress } from './httpTransport'

/**
 * An entity's subresources hang off the one address its identity has.
 *
 * A GSN goal selected on its diagram asked for its neighbourhood at `/api/entities/{id}/neighbors`.
 * Its id (`GSN@…#nodes/g11`) holds a slash, which the server decodes before routing, so that request
 * matched no route and answered 404 — while the goal's own read, which went through `entityAddress`,
 * worked. The neighbourhood is now built by the same function.
 */
describe('entityAddress', () => {
  const pathOf = (url: string): string => {
    const parsed = new URL(url)
    return `${decodeURIComponent(parsed.pathname)}${parsed.search}`
  }

  it('addresses an ordinary entity and its neighbourhood in the entity collection', () => {
    expect(pathOf(entityAddress('APP@1.a.thing'))).toBe('/api/entities/APP@1.a.thing')
    expect(pathOf(entityAddress('APP@1.a.thing', '/neighbors', { max_hops: 2 })))
      .toBe('/api/entities/APP@1.a.thing/neighbors?max_hops=2')
  })

  it('addresses a construct a diagram owns, and its neighbourhood, in its diagram', () => {
    const id = 'GSN@1781338120.3U4cRc.assurance-case#nodes/g11'
    expect(pathOf(entityAddress(id))).toBe('/api/diagrams/GSN@1781338120.3U4cRc.assurance-case/entities/nodes/g11')
    expect(pathOf(entityAddress(id, '/neighbors', { traversal: 'derived' })))
      .toBe('/api/diagrams/GSN@1781338120.3U4cRc.assurance-case/entities/nodes/g11/neighbors?traversal=derived')
  })

  it('never puts the slash of a held id inside one path segment', () => {
    const url = new URL(entityAddress('GSN@1.a.case#nodes/g11', '/neighbors'))
    expect(url.pathname).not.toContain('%2F')
    expect(url.pathname).not.toContain('%23')
  })
})
