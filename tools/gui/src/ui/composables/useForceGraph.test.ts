import { describe, expect, it } from 'vitest'
import { useForceGraph } from './useForceGraph'

describe('applyGroupClusterLayout', () => {
  it('spreads a multi-group population across more than one Y position', () => {
    const graph = useForceGraph(() => 1200, () => 800)
    const ids = ['alpha', 'beta', 'gamma'].flatMap((group) =>
      Array.from({ length: 6 }, (_, i) => `${group}-${i}`))
    for (const id of ids) graph.addNode({ id, label: id, type: 'X' })

    graph.applyGroupClusterLayout((id) => id.split('-')[0])

    const ys = new Set(graph.nodes.value.map((n) => n.y))
    expect(ys.size).toBeGreaterThan(1)
  })

  it('does not collapse every node onto a single horizontal line', () => {
    const graph = useForceGraph(() => 1200, () => 800)
    const ids = ['alpha', 'beta', 'gamma', 'delta'].flatMap((group) =>
      Array.from({ length: 4 }, (_, i) => `${group}-${i}`))
    for (const id of ids) graph.addNode({ id, label: id, type: 'X' })

    graph.applyGroupClusterLayout((id) => id.split('-')[0])

    const uniqueY = new Set(graph.nodes.value.map((n) => n.y))
    expect(uniqueY.size).toBeGreaterThan(1)
  })

  it('keeps a single small group\'s members near each other rather than spread the full canvas width', () => {
    const graph = useForceGraph(() => 1200, () => 800)
    for (const id of ['solo-0', 'solo-1', 'solo-2']) graph.addNode({ id, label: id, type: 'X' })

    graph.applyGroupClusterLayout(() => 'solo')

    const xs = graph.nodes.value.map((n) => n.x)
    expect(Math.max(...xs) - Math.min(...xs)).toBeLessThan(600)
  })
})

describe('applyRadialLayout', () => {
  it('positions the anchor at the reported canvas centre and rings farther nodes outward', () => {
    const graph = useForceGraph(() => 1200, () => 800)
    for (const id of ['anchor', 'near', 'far']) graph.addNode({ id, label: id, type: 'X' })

    const { cx, cy } = graph.applyRadialLayout(new Map([['anchor', 0], ['near', 1], ['far', 2]]), 150)

    expect({ cx, cy }).toEqual({ cx: 600, cy: 400 })
    const byId = new Map(graph.nodes.value.map((n) => [n.id, n]))
    expect({ x: byId.get('anchor')!.x, y: byId.get('anchor')!.y }).toEqual({ x: 600, y: 400 })
    expect(Math.hypot(byId.get('near')!.x - 600, byId.get('near')!.y - 400)).toBeCloseTo(150, 6)
    // Ring radii grow sub-linearly (spacing · Σ 0.75^k): hop 2 sits at 1.75 × spacing.
    expect(Math.hypot(byId.get('far')!.x - 600, byId.get('far')!.y - 400)).toBeCloseTo(262.5, 6)
    expect(graph.layoutMode.value).toBe('radial')
  })
})
