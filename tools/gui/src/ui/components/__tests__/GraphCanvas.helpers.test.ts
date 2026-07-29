/**
 * Pure geometry/presentation tests for the generic graph canvas helpers:
 * shape polygons, contrast text color, viewBox fitting, and label wrapping.
 */
import { describe, it, expect } from 'vitest'
import { contrastTextColor, edgePathFor, fitViewBox, nodeShapePoints, wrapLabel } from '../GraphCanvas.helpers'

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

  it('wraps at word boundaries up to two lines', () => {
    expect(wrapLabel('Canonical Per-Repo Artifact Index', 14, 2)).toEqual(['Canonical', 'Per-Repo…'])
  })

  it('ellipsizes when content remains beyond the last line', () => {
    const lines = wrapLabel('Architecture Management Platform Backend Service', 14, 2)
    expect(lines).toHaveLength(2)
    expect(lines[1].endsWith('…')).toBe(true)
  })

  it('hard-truncates a single overlong word', () => {
    const lines = wrapLabel('supercalifragilisticexpialidocious', 14, 2)
    expect(lines[0].length).toBeLessThanOrEqual(14)
    expect(lines[0].endsWith('…')).toBe(true)
  })
})

describe('edgePathFor', () => {
  const nodes = [
    { id: 'a', x: 0, y: 0 },
    { id: 'b', x: 0, y: 100 },
    { id: 'c', x: 100, y: 0 },
  ]

  it('returns empty string when an endpoint is missing', () => {
    expect(edgePathFor(nodes, { source: 'a', target: 'zzz' }, false)).toBe('')
  })

  it('stops a straight edge short of the target centre by the target radius', () => {
    // a→b is vertical over 100px; with radius 26 the endpoint is at y = 100 - 26 = 74.
    expect(edgePathFor(nodes, { source: 'a', target: 'b', }, false, 26)).toBe('M 0 0 L 0.00 74.00')
  })

  it('backs a cluster elbow off along the final vertical approach', () => {
    // Elbow into b (below): final V stops at 100 - 26 = 74, not at 100 (under the node).
    expect(edgePathFor(nodes, { source: 'c', target: 'b' }, true, 26)).toBe('M 100 0 V 50 H 0 V 74')
  })

  it('does not overshoot when the nodes are closer than the radius', () => {
    const near = [{ id: 'a', x: 0, y: 0 }, { id: 'b', x: 0, y: 10 }]
    // 10px apart, radius 26 — keep the full segment rather than inverting it.
    expect(edgePathFor(near, { source: 'a', target: 'b' }, false, 26)).toBe('M 0 0 L 0 10')
  })
})
