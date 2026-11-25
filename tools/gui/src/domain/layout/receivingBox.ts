/**
 * The box something new is added to (sketch 03·1–2): the innermost box drawn under a point, and what
 * that box admits. A box the renderer computes admits by its rule (`rule` on the geometry); a grouping
 * an author states admits by the rule it states, or anything when it lists its members; an element
 * drawn with its parts inside admits what it may contain, which only the ontology can answer, so it is
 * named here as the container's type and asked of the ontology by the caller.
 */
import type { AuthoredGroupingWire } from '../schemas/diagrams'
import type { GeometryBox, LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import type { Extent, Point } from './geometry'

/** What a box takes: anything, one layer, one element type, or the parts a container may hold. */
export type Admission =
  | { readonly kind: 'anything' }
  | { readonly kind: 'domain'; readonly domain: string }
  | { readonly kind: 'type'; readonly type: string }
  | { readonly kind: 'parts'; readonly container: string; readonly containerType: string }

/** The element a container box draws: its name and its type. */
export interface DrawnElement {
  readonly name: string
  readonly type: string
}

export interface ReceivingBox {
  readonly alias: string
  readonly label: string
  readonly admits: Admission
}

const holds = (extent: Extent, at: Point): boolean =>
  at.x >= extent.left && at.x <= extent.right && at.y >= extent.top && at.y <= extent.bottom

/** A rule as a stated grouping writes it, and as the geometry gives a computed box's: one key. */
const admittedBy = (rule: Readonly<Record<string, string>> | undefined): Admission => {
  if (rule?.type !== undefined) return { kind: 'type', type: rule.type }
  if (rule?.domain !== undefined) return { kind: 'domain', domain: rule.domain }
  return { kind: 'anything' }
}

/** The stated grouping *id*, at whatever depth the diagram states it. */
const statedGrouping = (
  groups: readonly AuthoredGroupingWire[], id: string,
): AuthoredGroupingWire | undefined => groups.reduce<AuthoredGroupingWire | undefined>(
  (found, group) => found ?? (group.id === id ? group : statedGrouping(group.groups ?? [], id)), undefined)

/**
 * The innermost box under *at* on the picture as it is placed now, and what it admits; null on open
 * paper. *elementOf* names the element a container box draws, and its type, by the geometry's key: a
 * container is called by its name, not by the label it is drawn with.
 */
export const receivingBoxAt = (
  geometry: LayoutGeometry, boxes: ReadonlyMap<string, Extent>, at: Point,
  stated: readonly AuthoredGroupingWire[], elementOf: (key: string) => DrawnElement | undefined,
): ReceivingBox | null => {
  const under = geometry.boxes.filter((box) => {
    const extent = boxes.get(box.alias)
    return extent !== undefined && holds(extent, at)
  })
  // The innermost is the one no other box under the point sits inside.
  const inner = under.find((box) => !under.some((other) => other.inside === box.alias))
  if (!inner) return null
  const element = inner.kind === 'element' && inner.key !== undefined ? elementOf(inner.key) : undefined
  return { alias: inner.alias, label: element?.name ?? inner.label, admits: admissionOf(inner, stated, element) }
}

const admissionOf = (
  box: GeometryBox, stated: readonly AuthoredGroupingWire[], element: DrawnElement | undefined,
): Admission => {
  if (box.kind === 'element') {
    return element ? { kind: 'parts', container: box.alias, containerType: element.type } : { kind: 'anything' }
  }
  if (box.kind === 'authored-grouping') {
    return admittedBy(box.key === undefined ? undefined : statedGrouping(stated, box.key)?.rule)
  }
  return admittedBy(box.rule)
}

/** Whether a type of layer *domain* may be added to a box admitting *admits*; *parts* are the
 * ontology's answer for a container, absent until it is known. */
export const admitsType = (
  admits: Admission, type: string, domain: string, parts?: ReadonlySet<string>,
): boolean => {
  switch (admits.kind) {
    case 'anything': return true
    case 'domain': return domain === admits.domain
    case 'type': return type === admits.type
    case 'parts': return parts?.has(type) ?? true
  }
}
