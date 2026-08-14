import { hierarchy } from 'd3-hierarchy'
import type { GraphEdge, GraphNode } from './useForceGraph'
import { nodeExtent } from '../components/graphNodeGeometry'

/** Cluster/dendrogram layout helpers for `useForceGraph` — split into their own module
 * purely to keep `useForceGraph.ts` under the project's per-file line limit; every export
 * here is pure (nodes/edges/viewport passed in, never read from a shared composable
 * closure) so it needs no Vue reactivity of its own. */

interface TreeNode { id: string; children?: TreeNode[] }
interface ClusterBox {
  key: string; ids: string[]; cols: number; cellW: number; cellH: number; width: number; height: number
}
type PosMap = Map<string, { x: number; y: number }>

/** Clearance between a node's drawn box and the edge of the cell holding it. */
const CELL_MARGIN_X = 34
const CELL_MARGIN_Y = 24

/**
 * How wide a node draws.
 *
 * Measured through the renderer's own geometry rather than guessed from the raw label
 * length. The previous estimate (`44 + label.length * 1.5`) described text that is never
 * drawn: labels are wrapped to two lines of fourteen characters, so a long name is *narrower*
 * on screen than the estimate and a short one in a wide cell wasted space. Two independent
 * descriptions of one thing, and the grid was built from the wrong one.
 */
const measuredNode = (nodes: readonly GraphNode[], id: string, isAnchor = false) => {
  const node = nodes.find((n) => n.id === id)
  return nodeExtent(node?.label ?? id, node?.type ?? '', isAnchor)
}

const estimateNodeWidth = (nodes: readonly GraphNode[], id: string): number =>
  Math.max(140, measuredNode(nodes, id).width)

const computeTreeMetrics = (
  nodes: readonly GraphNode[],
  node: TreeNode,
  depth: number,
  metrics: Map<string, { depth: number; width: number }>,
): number => {
  const children = node.children ?? []
  const childWidths = children.map((child) => computeTreeMetrics(nodes, child, depth + 1, metrics))
  const siblingGap = Math.max(36, Math.max(0, ...children.map((child) => estimateNodeWidth(nodes, child.id) * 0.15)))
  const subtreeWidth = children.length
    ? Math.max(
        estimateNodeWidth(nodes, node.id),
        childWidths.reduce((sum, width) => sum + width, 0) + siblingGap * (children.length - 1),
      )
    : estimateNodeWidth(nodes, node.id)
  metrics.set(node.id, { depth, width: subtreeWidth })
  return subtreeWidth
}

const assignTreePositions = (
  nodes: readonly GraphNode[],
  node: TreeNode,
  left: number,
  metrics: Map<string, { depth: number; width: number }>,
  posMap: PosMap,
  levelGap: number,
  topPad: number,
) => {
  const metric = metrics.get(node.id)
  if (!metric) return
  const children = node.children ?? []
  const x = left + metric.width / 2
  const y = topPad + metric.depth * levelGap
  posMap.set(node.id, { x, y })

  if (!children.length) return

  const siblingGap = Math.max(36, Math.max(0, ...children.map((child) => estimateNodeWidth(nodes, child.id) * 0.35)))
  let cursor = left
  for (const child of children) {
    const childMetric = metrics.get(child.id)
    if (!childMetric) continue
    assignTreePositions(nodes, child, cursor, metrics, posMap, levelGap, topPad)
    cursor += childMetric.width + siblingGap
  }
}

export const buildTree = (edges: readonly GraphEdge[], rootId: string): TreeNode => {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, [])
    if (!adj.has(e.target)) adj.set(e.target, [])
    adj.get(e.source)!.push(e.target)
    adj.get(e.target)!.push(e.source)
  }
  const visited = new Set<string>()
  const walk = (id: string): TreeNode => {
    visited.add(id)
    const kids = (adj.get(id) ?? []).filter((c) => !visited.has(c)).map(walk)
    return kids.length ? { id, children: kids } : { id }
  }
  return walk(rootId)
}

/** Buckets the current node set by `groupOf(id)` and sizes each bucket as its own
 *  roughly-square grid of cells — the member layout a group gets once it's placed. */
export const buildClusterBoxes = (
  nodes: readonly GraphNode[],
  groupOf: (id: string) => string,
  anchorIds: ReadonlySet<string> = new Set(),
  /** How much of the standard margin a cell is given, from the surface's spacing rung. */
  cellGap = 1,
): ClusterBox[] => {
  const groups = new Map<string, string[]>()
  for (const n of nodes) {
    const key = groupOf(n.id)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(n.id)
  }
  const sortedGroups = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))
  return sortedGroups.map(([key, ids]) => {
    // Both axes are driven by the tallest and widest member. Height used to be the constant
    // 90 while a node with a two-line label draws 83 tall and an anchor 99 — so every grid
    // was between seven pixels and negative sixteen pixels of clearance from overlapping,
    // and the anchor's row always did.
    const measured = ids.map((id) => measuredNode(nodes, id, anchorIds.has(id)))
    const cellW = Math.max(140, ...measured.map((m) => m.width)) + CELL_MARGIN_X * cellGap
    const cellH = Math.max(...measured.map((m) => m.height)) + CELL_MARGIN_Y * cellGap
    const cols = Math.max(1, Math.ceil(Math.sqrt(ids.length)))
    const rows = Math.ceil(ids.length / cols)
    return { key, ids, cellW, cellH, cols, width: cols * cellW, height: rows * cellH }
  })
}

/** Shelf-packs each group's box left to right, wrapping to a new row once the row
 *  outgrows a roughly-square target width — a group never shares a row-band with so many
 *  neighbours that it gets squeezed onto one axis, which is what a depth-keyed dendrogram
 *  layout did here previously: every leaf entity sat at the same tree depth regardless of
 *  its group, so they all collapsed onto one shared Y and only spread out along X. */
export const layoutGroupClusters = (
  boxes: readonly ClusterBox[],
  width: number,
  height: number,
): { posMap: PosMap; cx: number; cy: number } => {
  const leftPad = 140
  const topPad = 110
  const groupGap = 80
  const totalArea = boxes.reduce((sum, box) => sum + box.width * box.height, 0)
  const targetRowWidth = Math.max(width, Math.sqrt(totalArea) * 1.4)

  const posMap: PosMap = new Map()
  let rowX = leftPad
  let rowY = topPad
  let rowHeight = 0
  let maxX = leftPad
  for (const box of boxes) {
    if (rowX > leftPad && rowX + box.width > targetRowWidth) {
      rowX = leftPad
      rowY += rowHeight + groupGap
      rowHeight = 0
    }
    box.ids.forEach((id, i) => {
      const col = i % box.cols
      const row = Math.floor(i / box.cols)
      posMap.set(id, { x: rowX + col * box.cellW + box.cellW / 2, y: rowY + row * box.cellH + box.cellH / 2 })
    })
    rowX += box.width + groupGap
    rowHeight = Math.max(rowHeight, box.height)
    maxX = Math.max(maxX, rowX)
  }
  return { posMap, cx: Math.max(width, maxX), cy: Math.max(height, rowY + rowHeight + topPad) }
}

/**
 * Where a group sits in a banded layout: which stacked row, and whether it is lifted out
 * of the stack to one side.
 *
 * Supplied by the caller. This module lays out graphs for any domain — architecture,
 * assurance, anything a future module plugs in — so it must not know what the group keys
 * mean. The vocabulary that has an inherent ordering owns the mapping and injects it.
 */
export interface BandPlacement { band: number; side: 'left' | 'right' | null }

export const layoutBandedClusters = (
  boxes: readonly ClusterBox[],
  width: number,
  height: number,
  placementOf: (groupKey: string) => BandPlacement,
  anchorIds: ReadonlySet<string> = new Set(),
): { posMap: PosMap; cx: number; cy: number } => {
  const topPad = 110
  const bandGap = 70
  const groupGap = 80
  const sideGap = 120

  const stacked = boxes.filter((box) => placementOf(box.key).side === null)
  const sided = boxes.filter((box) => placementOf(box.key).side !== null)
  // Every band that anything wants to sit in, stacked or beside — a band named only by a side
  // group still needs a row of its own, or that group lands on top of a neighbouring band.
  const bands = [...new Set(boxes.map((box) => placementOf(box.key).band))].sort((a, b) => a - b)
  const axis = Math.max(width, 800) / 2

  const posMap: PosMap = new Map()

  /**
   * Move an anchor to the middle slot of its own grid before placing it.
   *
   * Centring the bands and then translating the whole layout cannot centre the anchor: a
   * translation moves the anchor and everything around it by the same amount, so their
   * offset never changes and the anchor stays wherever its grid happened to put it. It has
   * to be centred *within its box* first; the later translation then lines that column up
   * with the shared axis, and the figure reads as symmetric about the element it is about.
   */
  const anchorCentredIds = (box: ClusterBox): string[] => {
    const index = box.ids.findIndex((id) => anchorIds.has(id))
    if (index < 0) return box.ids
    const rest = box.ids.filter((id) => !anchorIds.has(id))
    const middle = Math.min(Math.floor(box.cols / 2), rest.length)
    return [...rest.slice(0, middle), box.ids[index], ...rest.slice(middle)]
  }

  const place = (box: ClusterBox, originX: number, originY: number) => {
    anchorCentredIds(box).forEach((id, i) => {
      const col = i % box.cols
      const row = Math.floor(i / box.cols)
      posMap.set(id, {
        x: originX + col * box.cellW + box.cellW / 2,
        y: originY + row * box.cellH + box.cellH / 2,
      })
    })
  }

  // Stacked core: one centred row per band.
  const bandBounds = new Map<number, { top: number; height: number; left: number; right: number }>()
  let cursorY = topPad
  for (const band of bands) {
    const inBand = stacked.filter((box) => placementOf(box.key).band === band)
    const beside = sided.filter((box) => placementOf(box.key).band === band)
    // The row is as tall as the tallest thing in it *including* what sits beside it. Sizing
    // it from the stacked boxes alone let a taller side group hang below the row and land on
    // the next band down — the bands were spaced for content that was not all of the content.
    const rowHeight = Math.max(0, ...inBand.map((box) => box.height), ...beside.map((box) => box.height))
    const rowWidth = inBand.reduce((sum, box) => sum + box.width, 0)
      + groupGap * Math.max(0, inBand.length - 1)
    let cursorX = axis - rowWidth / 2
    const left = cursorX
    for (const box of inBand) {
      place(box, cursorX, cursorY + (rowHeight - box.height) / 2)
      cursorX += box.width + groupGap
    }
    bandBounds.set(band, {
      top: cursorY, height: rowHeight, left,
      right: inBand.length > 0 ? cursorX - groupGap : axis,
    })
    cursorY += rowHeight + bandGap
  }

  // Side domains: beside the band they name, vertically centred on it.
  // Several groups may claim the same side of the same band; they queue outward from it
  // rather than stacking on the same coordinates.
  const sideCursor = new Map<string, number>()
  for (const box of sided) {
    const placement = placementOf(box.key)
    const bound = bandBounds.get(placement.band)!
    const key = `${placement.band}:${placement.side}`
    const used = sideCursor.get(key) ?? 0
    const originX = placement.side === 'left'
      ? bound.left - sideGap - box.width - used
      : bound.right + sideGap + used
    sideCursor.set(key, used + box.width + groupGap)
    place(box, originX, bound.top + (bound.height - box.height) / 2)
  }

  // Put the anchor on the axis. A single shift keeps every relative position intact.
  const anchorPos = [...anchorIds].map((id) => posMap.get(id)).find((pos) => pos !== undefined)
  if (anchorPos) {
    const shift = axis - anchorPos.x
    for (const [id, pos] of posMap) posMap.set(id, { x: pos.x + shift, y: pos.y })
  }

  const xs = [...posMap.values()].map((pos) => pos.x)
  return {
    posMap,
    cx: Math.max(width, xs.length ? Math.max(...xs) + topPad : width),
    cy: Math.max(height, cursorY + topPad),
  }
}

/** Concentric-ring layout keyed by hop distance: anchors (distance 0) sit at `center`
 *  (on a tight inner ring when there are several), a node at distance d sits on the ring
 *  of radius `d * ringSpacing`, and nodes without a distance (unreachable from any
 *  anchor) land together on one ring beyond the farthest reachable one. Ring members are
 *  ordered lexicographically by id — deterministic, and adjacent BFS siblings (which
 *  usually share an id prefix via their type/group) tend to stay adjacent on the ring. */
const RING_RADIUS_DECAY = 0.75

/**
 * Circumference a ring member is given, when nothing wider is asked for.
 *
 * A floor rather than the answer: what a member actually needs is the width of its own drawn
 * extent, label included, and `ringArcFor` measures that. This was a fixed 70 when every label was
 * wrapped to two lines of fourteen characters and so had a fixed width — once a label may be as
 * wide as its longest word, spacing by a constant puts a 150px label in a 70px slot and the ring
 * reads as one overlapping band.
 */
const MIN_RING_ARC = 70

/** The widest drawn extent among a ring's members, scaled by how much of it the rung grants. */
const ringArcFor = (
  ids: readonly string[], byId: ReadonlyMap<string, GraphNode>, labelArc: number,
): number => {
  const widths = ids.map((id) => {
    const node = byId.get(id)
    return node ? nodeExtent(node.label, node.type, false).width : 0
  })
  // Every member gets the widest member's arc: unequal arcs would put the labels at unequal
  // angles, and a ring whose spacing changes as it goes round reads as a mistake rather than as
  // information. A small gap, so neighbours are separated rather than merely not overlapping.
  return Math.max(MIN_RING_ARC, (Math.max(0, ...widths) + RING_ARC_GAP) * labelArc)
}

const RING_ARC_GAP = 16

/** Sub-linear ring radii: each additional hop adds a geometrically shrinking increment
 * (spacing · Σ decay^k), so deep neighborhoods stay compact instead of growing linearly
 * with hop count. A crowded ring is widened to give every member at least MIN_RING_ARC
 * of circumference, whichever radius is larger. */
const ringRadius = (
  ring: number, memberCount: number, ringSpacing: number, arcPerMember: number,
): number => {
  const base = ringSpacing * ((1 - RING_RADIUS_DECAY ** ring) / (1 - RING_RADIUS_DECAY))
  const crowdFit = (memberCount * arcPerMember) / (2 * Math.PI)
  return Math.max(base, crowdFit)
}

export const layoutRadialByDistance = (
  nodes: readonly GraphNode[],
  distances: ReadonlyMap<string, number>,
  center: { x: number; y: number },
  ringSpacing: number,
  labelArc = 1,
): PosMap => {
  const maxDistance = Math.max(0, ...distances.values())
  const unreachableRing = maxDistance + 1
  const rings = new Map<number, string[]>()
  for (const node of nodes) {
    const ring = distances.get(node.id) ?? unreachableRing
    if (!rings.has(ring)) rings.set(ring, [])
    rings.get(ring)!.push(node.id)
  }
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const posMap: PosMap = new Map()
  for (const [ring, ids] of rings) {
    ids.sort((a, b) => a.localeCompare(b))
    if (ring === 0 && ids.length === 1) {
      posMap.set(ids[0], { x: center.x, y: center.y })
      continue
    }
    const radius = ring === 0
      ? ringSpacing * 0.4
      : ringRadius(ring, ids.length, ringSpacing, ringArcFor(ids, byId, labelArc))
    ids.forEach((id, index) => {
      const angle = -Math.PI / 2 + (index / ids.length) * Math.PI * 2
      posMap.set(id, { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius })
    })
  }
  return posMap
}

export const layoutTree = (
  nodes: readonly GraphNode[],
  tree: TreeNode,
  width: number,
  height: number,
): { posMap: PosMap; cx: number; cy: number } => {
  const root = hierarchy(tree)
  const leftPad = 140
  const topPad = 110
  const rightPad = 140
  const bottomPad = 110
  const maxDepth = Math.max(...root.descendants().map((d) => d.depth), 0)
  const levelGap = Math.max(110, Math.min(180, width / Math.max(maxDepth + 1, 2)))
  const metrics = new Map<string, { depth: number; width: number }>()
  const totalWidth = computeTreeMetrics(nodes, tree, 0, metrics)
  const posMap: PosMap = new Map()
  assignTreePositions(nodes, tree, leftPad, metrics, posMap, levelGap, topPad)
  const canvasWidth = Math.max(width, totalWidth + leftPad + rightPad)
  const canvasHeight = Math.max(height, topPad + bottomPad + maxDepth * levelGap)
  return { posMap, cx: canvasWidth, cy: canvasHeight }
}
