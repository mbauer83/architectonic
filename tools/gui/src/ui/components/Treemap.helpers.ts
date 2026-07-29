/**
 * The treemap's geometry and text-fitting, and the shape it draws.
 *
 * Vocabulary-free by contract, like `DataTable` and `GroupedRowTree`: a caller hands over groups of
 * leaves that already carry their label, colour and weight, and this knows nothing about what a
 * leaf *is*. The architecture surface groups entities by domain and sizes them by connection count;
 * the assurance surface groups nodes by node type. Neither vocabulary appears here, because a
 * component that knew either would be wrong for the other one first.
 *
 * The geometry lives in this module rather than in the component so it can be tested: every rule
 * below is a decision about when a label would be unreadable, and those are exactly the decisions
 * that quietly rot as the layout changes.
 */

export interface TreemapLeaf {
  /** Stable identity; also what `select` emits. */
  key: string
  /** Primary text drawn in the tile. */
  label: string
  /** Secondary text, drawn only when the tile is big enough for both. */
  meta?: string
  /** Relative weight. Non-positive values still get a sliver — see `sizeOf`. */
  value: number
  color: string
}

export interface TreemapGroup {
  name: string
  color: string
  children: TreemapLeaf[]
}

/**
 * The weight a leaf occupies.
 *
 * A floor rather than the raw value, because an unconnected element is still a thing that exists:
 * at weight zero d3 gives it no area at all, so the surface would silently omit exactly the
 * elements most likely to need attention.
 */
export const sizeOf = (value: number): number => Math.max(value, 0.25)

export const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value))

/** Truncate to what fits, with an ellipsis — never overflow the tile. */
export const fitText = (text: string, width: number, fontSize: number): string => {
  const maxChars = Math.max(3, Math.floor(width / Math.max(fontSize * 0.62, 1)))
  return text.length > maxChars ? `${text.slice(0, maxChars - 1)}…` : text
}

export const groupFontSize = (width: number, height: number): number =>
  clamp(Math.min(width / 10, height * 0.4), 8, 12)

export interface LeafVisuals {
  iconSize: number
  left: number
  textX: number
  nameSize: number
  metaSize: number
  label: string
  showIcon: boolean
  showName: boolean
  showMeta: boolean
}

/**
 * What of a tile's contents is drawn at its current size and zoom.
 *
 * Each `show*` threshold is the point below which that element would be illegible rather than
 * small — a clipped glyph and a one-character name are worse than an empty tile, because they look
 * like information.
 */
export const leafVisuals = (
  width: number,
  height: number,
  label: string,
  zoom: number,
): LeafVisuals => {
  const fits = (minW: number, minH: number) => width * zoom >= minW && height * zoom >= minH
  const iconSize = clamp(Math.min(width * 0.18, height * 0.46), 8, 14)
  const gap = clamp(iconSize * 0.45, 4, 8)
  const left = 8
  const textX = left + iconSize + gap
  const textWidth = Math.max(0, width - textX - 6)
  const nameSize = clamp(Math.min(height * 0.24, textWidth / 7.2), 7, 12)
  const metaSize = clamp(Math.min(height * 0.18, textWidth / 13), 6, 10)
  return {
    iconSize,
    left,
    textX,
    nameSize,
    metaSize,
    label: fitText(label, textWidth, nameSize),
    showIcon: fits(24, 20),
    showName: textWidth > 18 && fits(62, 30),
    showMeta: textWidth > 30 && fits(88, 44),
  }
}

export const showGroupLabel = (width: number, height: number, zoom: number): boolean =>
  width * zoom >= 110 && height * zoom >= 42

export const clampZoom = (next: number): number => Math.min(12, Math.max(1, next))

/** A drag that moved this far is a pan, not a click on the tile under the cursor. */
export const PAN_THRESHOLD_PX = 4

export const movedFar = (
  from: { x: number; y: number },
  to: { x: number; y: number },
): boolean => Math.hypot(to.x - from.x, to.y - from.y) > PAN_THRESHOLD_PX

/** Group leaves into a treemap tree, in the order the caller's key comparator gives. */
export const groupLeaves = <T>(
  items: readonly T[],
  leafOf: (item: T) => TreemapLeaf,
  groupOf: (item: T) => { name: string; color: string },
): TreemapGroup[] => {
  const groups = new Map<string, TreemapGroup>()
  for (const item of items) {
    const { name, color } = groupOf(item)
    const existing = groups.get(name)
    if (existing) existing.children.push(leafOf(item))
    else groups.set(name, { name, color, children: [leafOf(item)] })
  }
  // Groups alphabetical so the picture is stable between loads; leaves heaviest first, so the
  // element a reader is most likely looking for is where they look first.
  return [...groups.values()]
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((group) => ({
      ...group,
      children: [...group.children].sort(
        (left, right) => right.value - left.value || left.label.localeCompare(right.label),
      ),
    }))
}
