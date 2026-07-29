/**
 * The treemap's geometry, and the assurance vocabulary that feeds it.
 *
 * Every threshold below decides whether a tile's contents would be readable or merely present. A
 * clipped glyph and a one-character name are worse than an empty tile, because they look like
 * information — so the rules are stated once, here, rather than inline in a template where they rot.
 */
import { describe, expect, it } from 'vitest'
import {
  PAN_THRESHOLD_PX,
  clamp,
  clampZoom,
  fitText,
  groupLeaves,
  leafVisuals,
  movedFar,
  showGroupLabel,
  sizeOf,
  type TreemapLeaf,
} from '../Treemap.helpers'
import {
  UNKNOWN_TYPE_COLOR,
  assuranceTreemapGroups,
  connectionTotal,
  nodeTypeColor,
  nodeTypeLabel,
  type AssuranceTreemapNode,
} from '../AssuranceTreemap.helpers'

describe('sizeOf', () => {
  it('gives an unconnected item a sliver rather than no area', () => {
    /* At weight zero d3 allocates nothing, so the surface would silently omit exactly the elements
       most likely to need attention. */
    expect(sizeOf(0)).toBeGreaterThan(0)
    expect(sizeOf(-5)).toBeGreaterThan(0)
  })

  it('passes a real weight through', () => {
    expect(sizeOf(7)).toBe(7)
  })
})

describe('fitText', () => {
  it('leaves text that fits alone', () => {
    expect(fitText('Key store', 400, 10)).toBe('Key store')
  })

  it('truncates with an ellipsis rather than overflowing the tile', () => {
    const fitted = fitText('An extremely long element name that cannot fit', 60, 10)

    expect(fitted.endsWith('…')).toBe(true)
    expect(fitted.length).toBeLessThan('An extremely long element name that cannot fit'.length)
  })

  it('never returns nothing, however narrow the tile', () => {
    expect(fitText('Anything', 1, 40).length).toBeGreaterThan(0)
  })
})

describe('leafVisuals', () => {
  it('draws nothing but the block in a tile too small to label', () => {
    const visuals = leafVisuals(10, 8, 'Key store', 1)

    expect(visuals.showIcon).toBe(false)
    expect(visuals.showName).toBe(false)
    expect(visuals.showMeta).toBe(false)
  })

  it('adds the name, then the meta line, as the tile grows', () => {
    expect(leafVisuals(70, 32, 'Key store', 1).showName).toBe(true)
    expect(leafVisuals(70, 32, 'Key store', 1).showMeta).toBe(false)
    expect(leafVisuals(200, 90, 'Key store', 1).showMeta).toBe(true)
  })

  it('counts zoom, so zooming in reveals labels rather than only enlarging blocks', () => {
    expect(leafVisuals(20, 16, 'Key store', 1).showIcon).toBe(false)
    expect(leafVisuals(20, 16, 'Key store', 4).showIcon).toBe(true)
  })

  it('keeps the text clear of the glyph', () => {
    const visuals = leafVisuals(200, 90, 'Key store', 1)

    expect(visuals.textX).toBeGreaterThan(visuals.left + visuals.iconSize)
  })
})

describe('showGroupLabel', () => {
  it('labels a group only when the heading would be readable', () => {
    expect(showGroupLabel(40, 20, 1)).toBe(false)
    expect(showGroupLabel(200, 80, 1)).toBe(true)
  })
})

describe('clamp and clampZoom', () => {
  it('bounds a value', () => {
    expect(clamp(5, 1, 3)).toBe(3)
    expect(clamp(0, 1, 3)).toBe(1)
  })

  it('never zooms out past the fitted view or in past a usable limit', () => {
    expect(clampZoom(0.1)).toBe(1)
    expect(clampZoom(9999)).toBe(12)
  })
})

describe('movedFar', () => {
  it('treats a still press as a click and a travelled one as a pan', () => {
    expect(movedFar({ x: 0, y: 0 }, { x: 1, y: 1 })).toBe(false)
    expect(movedFar({ x: 0, y: 0 }, { x: PAN_THRESHOLD_PX + 2, y: 0 })).toBe(true)
  })
})

describe('groupLeaves', () => {
  const leafOf = (n: { id: string; label: string; weight: number }): TreemapLeaf =>
    ({ key: n.id, label: n.label, value: n.weight, color: '#000' })

  it('groups alphabetically and orders leaves heaviest first', () => {
    const groups = groupLeaves(
      [
        { id: 'a', label: 'Light', weight: 1, group: 'Zulu' },
        { id: 'b', label: 'Heavy', weight: 9, group: 'Alpha' },
        { id: 'c', label: 'Middle', weight: 5, group: 'Alpha' },
      ],
      leafOf,
      (item) => ({ name: item.group, color: '#000' }),
    )

    expect(groups.map((g) => g.name)).toEqual(['Alpha', 'Zulu'])
    expect(groups[0].children.map((l) => l.label)).toEqual(['Heavy', 'Middle'])
  })

  it('breaks a weight tie by label, so the picture is stable between loads', () => {
    const groups = groupLeaves(
      [
        { id: 'b', label: 'Beta', weight: 3, group: 'G' },
        { id: 'a', label: 'Alpha', weight: 3, group: 'G' },
      ],
      leafOf,
      () => ({ name: 'G', color: '#000' }),
    )

    expect(groups[0].children.map((l) => l.label)).toEqual(['Alpha', 'Beta'])
  })
})

// ── The assurance vocabulary ──────────────────────────────────────────────────

const node = (over: Partial<AssuranceTreemapNode> = {}): AssuranceTreemapNode => ({
  node_id: 'HAZ@1', node_type: 'hazard', name: 'Key unavailable', conn_in: 2, conn_out: 1, ...over,
})

describe('the assurance treemap vocabulary', () => {
  it('groups by node type, which every node has', () => {
    /* Concern class is empty on most nodes, so grouping by it would put the majority in one
       anonymous bucket. */
    const groups = assuranceTreemapGroups([
      node(),
      node({ node_id: 'LSS@1', node_type: 'loss', name: 'Work unrecoverable' }),
      node({ node_id: 'HAZ@2', name: 'Key mismatched' }),
    ])

    expect(groups.map((g) => g.name)).toEqual(['Hazard', 'Loss'])
    expect(groups[0].children).toHaveLength(2)
  })

  it('sizes a node by its visible connections', () => {
    expect(connectionTotal(node({ conn_in: 4, conn_out: 3 }))).toBe(7)
    expect(connectionTotal({ node_id: 'X', node_type: 'hazard', name: 'X' })).toBe(0)
  })

  it('still places an unconnected node', () => {
    const groups = assuranceTreemapGroups([node({ conn_in: 0, conn_out: 0 })])

    expect(groups[0].children[0].value).toBe(0)
    expect(sizeOf(groups[0].children[0].value)).toBeGreaterThan(0)
  })

  it('labels a type readably rather than showing its slug', () => {
    expect(nodeTypeLabel('unsafe-control-action')).toBe('Unsafe control action')
    expect(nodeTypeLabel('')).toBe('Untyped')
  })

  it('colours the consequence spine apart from the response', () => {
    expect(nodeTypeColor('hazard')).not.toBe(nodeTypeColor('assurance-constraint'))
  })

  it('marks a type it has no colour for as unclassified rather than miscolouring it', () => {
    expect(nodeTypeColor('a-type-from-the-future')).toBe(UNKNOWN_TYPE_COLOR)
  })

  it('falls back to the id when a node has no name', () => {
    const groups = assuranceTreemapGroups([node({ name: '' })])

    expect(groups[0].children[0].label).toBe('HAZ@1')
  })

  it('is empty for an empty list', () => {
    expect(assuranceTreemapGroups([])).toEqual([])
  })
})
