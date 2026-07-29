import { describe, expect, it } from 'vitest'
import { layoutRadialByDistance } from './useForceGraphLayout'
import type { GraphNode } from './useForceGraph'

const mkNode = (id: string): GraphNode => ({
  id, label: id, type: 'X', x: 0, y: 0, vx: 0, vy: 0, expanded: false, pinned: false,
})

const center = { x: 500, y: 400 }
const spacing = 100

const radiusOf = (pos: { x: number; y: number } | undefined) => {
  if (!pos) throw new Error('node missing from position map')
  return Math.hypot(pos.x - center.x, pos.y - center.y)
}

describe('layoutRadialByDistance', () => {
  it('places a single anchor exactly at the center', () => {
    const posMap = layoutRadialByDistance(
      [mkNode('anchor'), mkNode('near')],
      new Map([['anchor', 0], ['near', 1]]),
      center, spacing,
    )
    expect(posMap.get('anchor')).toEqual(center)
  })

  it('grows ring radii sub-linearly: full spacing for hop 1, geometrically shrinking increments after', () => {
    const nodes = ['anchor', 'one-a', 'one-b', 'two', 'three'].map(mkNode)
    const distances = new Map([['anchor', 0], ['one-a', 1], ['one-b', 1], ['two', 2], ['three', 3]])
    const posMap = layoutRadialByDistance(nodes, distances, center, spacing)
    const r1 = radiusOf(posMap.get('one-a'))
    const r2 = radiusOf(posMap.get('two'))
    const r3 = radiusOf(posMap.get('three'))
    expect(radiusOf(posMap.get('one-b'))).toBeCloseTo(r1, 6)
    expect(r1).toBeCloseTo(spacing, 6)
    expect(r2).toBeCloseTo(spacing * 1.75, 6)
    expect(r3).toBeCloseTo(spacing * 2.3125, 6)
    // Each additional hop adds strictly less radius than the previous one.
    expect(r3 - r2).toBeLessThan(r2 - r1)
  })

  it('widens a crowded ring so every member gets a minimum arc of circumference', () => {
    const members = Array.from({ length: 24 }, (_, i) => `m${String(i).padStart(2, '0')}`)
    const nodes = ['anchor', ...members].map(mkNode)
    const distances = new Map<string, number>([['anchor', 0], ...members.map((id): [string, number] => [id, 1])])
    const posMap = layoutRadialByDistance(nodes, distances, center, spacing)
    const radius = radiusOf(posMap.get(members[0]))
    expect(radius).toBeGreaterThan(spacing)
    expect(radius * 2 * Math.PI).toBeGreaterThanOrEqual(members.length * 70 - 1e-6)
  })

  it('spreads ring members angularly so they never collide', () => {
    const nodes = ['anchor', 'one-a', 'one-b', 'one-c'].map(mkNode)
    const distances = new Map([['anchor', 0], ['one-a', 1], ['one-b', 1], ['one-c', 1]])
    const posMap = layoutRadialByDistance(nodes, distances, center, spacing)
    const positions = ['one-a', 'one-b', 'one-c'].map((id) => posMap.get(id)!)
    const distinct = new Set(positions.map((pos) => `${pos.x.toFixed(3)},${pos.y.toFixed(3)}`))
    expect(distinct.size).toBe(3)
  })

  it('puts nodes without a distance on one ring beyond the farthest reachable one', () => {
    const nodes = ['anchor', 'far', 'island'].map(mkNode)
    const distances = new Map([['anchor', 0], ['far', 3]])
    const posMap = layoutRadialByDistance(nodes, distances, center, spacing)
    expect(radiusOf(posMap.get('island'))).toBeGreaterThan(radiusOf(posMap.get('far')))
  })

  it('keeps multiple anchors near the center on a tight inner ring, not stacked', () => {
    const nodes = ['anchor-a', 'anchor-b', 'one'].map(mkNode)
    const distances = new Map([['anchor-a', 0], ['anchor-b', 0], ['one', 1]])
    const posMap = layoutRadialByDistance(nodes, distances, center, spacing)
    const rA = radiusOf(posMap.get('anchor-a'))
    const rB = radiusOf(posMap.get('anchor-b'))
    expect(rA).toBeLessThan(spacing / 2)
    expect(rB).toBeLessThan(spacing / 2)
    expect(posMap.get('anchor-a')).not.toEqual(posMap.get('anchor-b'))
  })

  it('is deterministic regardless of node insertion order', () => {
    const distances = new Map([['anchor', 0], ['b', 1], ['a', 1], ['c', 1]])
    const forward = layoutRadialByDistance(['anchor', 'a', 'b', 'c'].map(mkNode), distances, center, spacing)
    const reversed = layoutRadialByDistance(['c', 'b', 'a', 'anchor'].map(mkNode), distances, center, spacing)
    for (const id of ['anchor', 'a', 'b', 'c']) {
      expect(forward.get(id)).toEqual(reversed.get(id))
    }
  })
})
