/**
 * Banded cluster layout: position has to mean something.
 *
 * A generic packer places groups in whatever order it walked them, so a reader cannot tell
 * why anything sits where it does. Banding exists to make the vertical axis carry the
 * caller's own ordering, and to put the element the view is *about* where the eye starts.
 */
import { describe, expect, it } from 'vitest'
import { buildClusterBoxes, layoutBandedClusters, type BandPlacement } from '../useForceGraphLayout'
import type { GraphNode } from '../useForceGraph'

const node = (id: string, label = id): GraphNode =>
  ({ id, label, type: id.slice(0, 3), x: 0, y: 0, vx: 0, vy: 0 }) as GraphNode

/** motivation above application, with "shared" lifted out to the side. */
const placement = (key: string): BandPlacement =>
  key === 'shared' ? { band: 1, side: 'left' } : { band: { motivation: 0, application: 2 }[key] ?? 9, side: null }

const layout = (groups: Record<string, string[]>, anchors: string[] = []) => {
  const ids = Object.entries(groups).flatMap(([, members]) => members)
  const groupOf = (id: string) =>
    Object.entries(groups).find(([, members]) => members.includes(id))?.[0] ?? 'other'
  const boxes = buildClusterBoxes(ids.map((id) => node(id)), groupOf)
  return layoutBandedClusters(boxes, 1000, 700, placement, new Set(anchors))
}

describe('band ordering', () => {
  it('places an earlier band above a later one', () => {
    const { posMap } = layout({ motivation: ['MOT1', 'MOT2'], application: ['APP1', 'APP2'] })

    expect(posMap.get('MOT1')!.y).toBeLessThan(posMap.get('APP1')!.y)
  })

  it('keeps members of one band on the same row', () => {
    const { posMap } = layout({ motivation: ['MOT1', 'MOT2'], application: ['APP1'] })

    expect(posMap.get('MOT1')!.y).toBe(posMap.get('MOT2')!.y)
  })

  it('lifts a side group out of the stack', () => {
    const { posMap } = layout({ motivation: ['MOT1'], application: ['APP1'], shared: ['SHR1'] })

    // Beside the stack, not above or below it.
    expect(posMap.get('SHR1')!.x).toBeLessThan(posMap.get('MOT1')!.x)
  })
})

describe('anchor placement', () => {
  it('centres the anchor on the content, not merely on an axis', () => {
    // A translation moves the anchor and its surroundings equally, so centring has to happen
    // inside the anchor's own grid — otherwise it stays wherever the grid put it.
    const { posMap } = layout(
      { motivation: ['MOT1', 'MOT2', 'MOT3', 'MOT4', 'MOT5'], application: ['APP1', 'APP2'] },
      ['MOT3'],
    )
    const xs = [...posMap.values()].map((p) => p.x)
    const centre = (Math.min(...xs) + Math.max(...xs)) / 2

    expect(Math.abs(posMap.get('MOT3')!.x - centre)).toBeLessThan(1)
  })

  it('leaves an unanchored layout alone', () => {
    const { posMap } = layout({ motivation: ['MOT1', 'MOT2'] })

    expect(posMap.size).toBe(2)
  })
})

describe('wrapping', () => {
  it('wraps a large group into a grid rather than one long row', () => {
    const ids = Array.from({ length: 36 }, (_, i) => `APP${i}`)
    const { posMap } = layout({ application: ids })

    const rows = new Set([...posMap.values()].map((p) => Math.round(p.y)))
    const widest = Math.max(...[...rows].map((y) =>
      [...posMap.values()].filter((p) => Math.round(p.y) === y).length))

    expect(rows.size).toBeGreaterThan(1)
    expect(widest).toBeLessThan(ids.length)
  })
})
