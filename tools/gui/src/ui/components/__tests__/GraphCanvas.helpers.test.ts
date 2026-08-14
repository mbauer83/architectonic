/**
 * Pure geometry/presentation tests for the generic graph canvas helpers:
 * shape polygons, contrast text color, viewBox fitting, and label wrapping.
 */
import { describe, it, expect } from 'vitest'
import { contrastTextColor, edgePathFor, fitViewBox, nodeShapePoints, wrapLabel } from '../GraphCanvas.helpers'
import { ANCHOR_HALO_RADIUS, NODE_SHAPE_RADIUS, edgeEndRadius } from '../graphNodeGeometry'

describe('contrastTextColor', () => {
  it('uses white text on dark fills and dark ink on light fills', () => {
    expect(contrastTextColor('#dc2626')).toBe('#ffffff')
    expect(contrastTextColor('#4f6d83')).toBe('#ffffff')
    expect(contrastTextColor('#fbbf24')).toBe('#252327')
    expect(contrastTextColor('#ffffff')).toBe('#252327')
  })

  it('defaults to dark ink for non-hex input', () => {
    expect(contrastTextColor('neutral')).toBe('#252327')
  })
})

describe('nodeShapePoints', () => {
  it('produces a distinct point count per shape', () => {
    expect(nodeShapePoints('triangle', 24).split(' ')).toHaveLength(3)
    expect(nodeShapePoints('diamond', 24).split(' ')).toHaveLength(4)
    expect(nodeShapePoints('square', 24).split(' ')).toHaveLength(4)
    expect(nodeShapePoints('circle', 24).split(' ')).toHaveLength(24)
  })

  it('gives diamond and square the same vertex count but a different orientation', () => {
    expect(nodeShapePoints('diamond', 24)).not.toBe(nodeShapePoints('square', 24))
  })
})

describe('fitViewBox', () => {
  it('bounds every node with padding, aspect-corrected to the container', () => {
    const box = fitViewBox([{ x: 0, y: 0 }, { x: 1000, y: 100 }], 800, 600, 50)
    expect(box.x).toBe(-50)
    expect(box.w).toBe(1100)
    // Content is wider than the container ratio → height is corrected up to match.
    expect(box.h).toBeCloseTo(1100 / (800 / 600))
    // Every node stays inside the box.
    expect(box.y).toBeLessThan(0)
    expect(box.y + box.h).toBeGreaterThan(100)
  })

  it('falls back to the container rect when there is nothing to fit', () => {
    expect(fitViewBox([], 800, 600)).toEqual({ x: 0, y: 0, w: 800, h: 600 })
  })
})

describe('wrapLabel', () => {
  it('keeps short labels on one line', () => {
    expect(wrapLabel('Query Engine')).toEqual(['Query Engine'])
  })

  it('wraps at word boundaries', () => {
    expect(wrapLabel('Canonical Per-Repo Artifact Index', 14)).toEqual([
      'Canonical', 'Per-Repo', 'Artifact Index',
    ])
  })

  it('keeps every word, however many lines that takes', () => {
    // The whole point: a label shown as "Architecture…" cannot be read away from the application
    // that drew it, and an exported picture of the graph is then unnamed circles.
    const label = 'Architecture Management Platform Backend Service'
    const lines = wrapLabel(label)

    expect(lines.join(' ')).toBe(label)
    expect(lines.some((line) => line.includes('…'))).toBe(false)
  })

  it('reproduces the longest label this repository actually carries', () => {
    const label = 'Provide Governed Self-Service Read Access to Architecture for Teams & Agents'

    expect(wrapLabel(label).join(' ')).toBe(label)
  })

  it('lets a word longer than the width overflow rather than cutting it', () => {
    // Cutting mid-word produced misreadings that reached real review artifacts. A word nothing can
    // wrap is better wide than wrong.
    const lines = wrapLabel('supercalifragilisticexpialidocious', 14)

    expect(lines).toEqual(['supercalifragilisticexpialidocious'])
  })

  it('answers an empty label with one empty line rather than nothing to draw', () => {
    expect(wrapLabel('')).toEqual([''])
  })
})

describe('edgePathFor', () => {
  const nodes = [
    { id: 'a', x: 0, y: 0 },
    { id: 'b', x: 0, y: 100 },
    { id: 'c', x: 100, y: 0 },
  ]
  /** Every node the same size, so the arithmetic below is about the rule and not about anchors. */
  const uniform = (radius: number) => () => radius

  it('returns empty string when an endpoint is missing', () => {
    expect(edgePathFor(nodes, { source: 'a', target: 'zzz' }, false)).toBe('')
  })

  it('stops a straight edge short of both centres, not only the target', () => {
    // a→b is vertical over 100px; with radius 26 at each end the segment runs y = 26 to y = 74.
    // The source end used to start at the centre, putting every source marker under its node.
    expect(edgePathFor(nodes, { source: 'a', target: 'b' }, false, uniform(26)))
      .toBe('M 0.00 26.00 L 0.00 74.00')
  })

  it('gives each end the radius of its own node', () => {
    // The anchor is larger, and which end it sits at decides which end backs off further.
    const radii = (id: string) => (id === 'a' ? 34 : 26)

    expect(edgePathFor(nodes, { source: 'a', target: 'b' }, false, radii))
      .toBe('M 0.00 34.00 L 0.00 74.00')
    expect(edgePathFor(nodes, { source: 'b', target: 'a' }, false, radii))
      .toBe('M 0.00 74.00 L 0.00 34.00')
  })

  it('backs a cluster elbow off at both the departure and the approach', () => {
    // Elbow c→b: leaves c downward at y = 0 + 26, arrives at b from above at y = 100 - 26.
    expect(edgePathFor(nodes, { source: 'c', target: 'b' }, true, uniform(26)))
      .toBe('M 100 26 V 50 H 0 V 74')
  })

  it('leaves a cluster departure at the centre when the first segment is too short for it', () => {
    // c→a is horizontal: midY equals both y values, so there is no vertical room to back off.
    expect(edgePathFor(nodes, { source: 'c', target: 'a' }, true, uniform(26)))
      .toBe('M 100 0 V 0 H 0 V 0')
  })

  it('does not overshoot when the nodes are closer than the two radii together', () => {
    const near = [{ id: 'a', x: 0, y: 0 }, { id: 'b', x: 0, y: 10 }]
    // 10px apart, 52px of back-off wanted — keep the full segment rather than inverting it.
    expect(edgePathFor(near, { source: 'a', target: 'b' }, false, uniform(26))).toBe('M 0 0 L 0 10')
  })

  it('backs off when the nodes clear both radii but not twice the larger one', () => {
    // 60px apart with 26 at each end: 8px of line left, which is a line, so both ends back off.
    const apart = [{ id: 'a', x: 0, y: 0 }, { id: 'b', x: 0, y: 60 }]

    expect(edgePathFor(apart, { source: 'a', target: 'b' }, false, uniform(26)))
      .toBe('M 0.00 26.00 L 0.00 34.00')
  })
})

describe('edgeEndRadius', () => {
  it('derives the back-off from the shape it has to clear, rather than restating it', () => {
    expect(edgeEndRadius(false)).toBeGreaterThan(NODE_SHAPE_RADIUS)
    expect(edgeEndRadius(true)).toBeGreaterThan(ANCHOR_HALO_RADIUS)
  })

  it('gives an anchor more room, because an anchor draws a larger ring', () => {
    expect(edgeEndRadius(true)).toBeGreaterThan(edgeEndRadius(false))
  })
})
