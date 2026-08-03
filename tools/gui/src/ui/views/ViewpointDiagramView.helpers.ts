/**
 * Pure helpers for the ad-hoc `diagram` execution representation: synthesizes the minimal
 * `DiagramContextEntity`/`DiagramConnection` shapes the generic graphviz/PlantUML element mapper
 * (`graphvizElementMapping.ts`) needs to resolve SVG elements back to artifact ids, plus
 * the `node_color`/`edge_color`/`edge_emphasis` highlight-overlay application — the same
 * client-side technique a real diagram's ghost/hide overlay uses, never baked into the
 * rendered PUML.
 */

import type { ConnectionItemSummary, DiagramConnection, EntityItemSummary, DiagramContextEntity, ProjectedOccurrence } from '../../domain'
import type { StyleValue } from '../../domain/schemas/viewpoints'
import { resolveStyleColor, styleTokenString, tokenEdgeEmphasis } from '../lib/viewpointStyleTokens'
import { resolveElementMap } from '../lib/diagramViewerExtensions'

/** `graphvizMapElements` reads only `artifact_id`/`display_alias`; `display_alias` must be
 * the rendered SVG's real PlantUML alias (`execute_viewpoint_diagram`'s `entity_aliases`
 * response field — never the raw artifact id, which the ad-hoc renderer never uses as an
 * alias), or click-to-select never resolves any SVG element back to its entity. Falls back
 * to the raw id only when the map has no entry (e.g. an entity dropped from the final
 * render), matching the same stub convention `EditMatrixView.vue` uses for its picker. */
export const toDiagramContextEntityStub = (
  entity: EntityItemSummary,
  aliasById: ReadonlyMap<string, string> = new Map(),
): DiagramContextEntity => ({
  artifact_id: entity.id, artifact_type: entity.type, name: entity.name,
  display_alias: aliasById.get(entity.id) ?? entity.id, version: '', status: '', domain: '', subdomain: '', path: '', specializations: [],
  // Execution items carry no tier; the stub exists only for alias resolution, so the
  // required list-contract flag defaults to the engagement tier.
  is_global: false,
})

/** `nameById` fills in the sidebar's connection-flow display (`source_name`/`target_name`);
 * `aliasById` resolves `source_alias`/`target_alias` the same way `toDiagramContextEntityStub`
 * does — both fall back to the raw id when the lookup has no entry. `certainty`/`hops`/
 * `via_connection_ids` carry straight through from the execution result unchanged (`null`/
 * empty for a real, modeled connection) — the sidebar uses `certainty` to decide whether
 * to offer the witness chain. */
export const toDiagramConnectionStub = (
  connection: ConnectionItemSummary,
  nameById: ReadonlyMap<string, string> = new Map(),
  aliasById: ReadonlyMap<string, string> = new Map(),
): DiagramConnection => ({
  artifact_id: connection.id, source: connection.source, target: connection.target, conn_type: connection.type,
  source_alias: aliasById.get(connection.source) ?? connection.source,
  target_alias: aliasById.get(connection.target) ?? connection.target,
  version: '', status: '', path: '', content_text: '',
  source_name: nameById.get(connection.source) ?? connection.source,
  target_name: nameById.get(connection.target) ?? connection.target,
  certainty: connection.certainty,
  hops: connection.hops,
  via_connection_ids: connection.via_connection_ids,
})

/** Applies an override only when a value is given — NEVER clears, since `shape.style` is
 * the SAME `style="..."` attribute PlantUML already populated with the notation's native
 * stroke (e.g. every connector line's `fill="none"` relies entirely on its own native
 * stroke for visibility). `style.removeProperty` can't distinguish "an overlay I set
 * earlier" from "the renderer's own native declaration" once they share one attribute, so
 * clearing unconditionally would delete native styling wherever no overlay applies — which
 * is every unstyled connection/entity, i.e. almost always. Each execution renders a fresh
 * SVG via `v-html`, so there is never a stale prior overlay on this element to revert. */
const applyStrokeOverride = (shape: SVGElement, color: string | null, width: string | null): void => {
  if (color !== null) shape.style.setProperty('stroke', color, 'important')
  if (width !== null) shape.style.setProperty('stroke-width', width, 'important')
}

const shapeChildren = (el: Element): SVGElement[] =>
  [...el.querySelectorAll('rect, polygon, path')].filter((n): n is SVGElement => n instanceof SVGElement)

/** `node_color` highlight overlay: a colored outline on the node's shape children, fixed
 * notation (fill/shape) otherwise untouched — an overlay, not a notation change. */
export const applyNodeColorOverlay = (elems: readonly Element[], value: StyleValue | undefined): void => {
  if (value === undefined) return
  for (const el of elems) {
    for (const shape of shapeChildren(el)) applyStrokeOverride(shape, resolveStyleColor(value), '3')
  }
}

/** `edge_color`/`edge_emphasis` highlight overlay, mirroring the exploration surface's
 * `edgeVisualFor` mapping (`GraphExploreView.helpers.ts`) but applied to real SVG path
 * elements instead of the custom force-graph renderer. */
export const applyEdgeHighlightOverlay = (
  elems: readonly Element[],
  colorValue: StyleValue | undefined,
  emphasisValue: StyleValue | undefined,
): void => {
  if (colorValue === undefined && emphasisValue === undefined) return
  const emphasis = emphasisValue !== undefined ? tokenEdgeEmphasis(styleTokenString(emphasisValue)) : null
  for (const el of elems) {
    for (const shape of shapeChildren(el)) {
      applyStrokeOverride(
        shape,
        colorValue !== undefined ? resolveStyleColor(colorValue) : null,
        emphasis ? String(emphasis.strokeWidth) : null,
      )
      if (emphasis?.dashArray !== undefined) shape.style.setProperty('stroke-dasharray', emphasis.dashArray, 'important')
    }
  }
}

export const projectionByItemId = (items: readonly ProjectedOccurrence[]): ReadonlyMap<string, ProjectedOccurrence> =>
  new Map(items.map((item) => [item.item_id, item]))

/** Distinct accent for the anchor marker — deliberately outside the style-token palette
 * (`viewpointStyleTokens.ts`) so an anchor stays identifiable no matter which `node_color`
 * overlay token also applies to the same entity. */
export const ANCHOR_MARKER_COLOR = '#7c3aed'

/** Narrows the mapped node elements down to the execution's anchor entities (the ids the
 * `entity-id` parameters resolved to), preserving anchor order. An anchor id with no
 * matched SVG element (e.g. dropped from the final render) contributes nothing. */
export const resolveAnchorElements = (
  anchorIds: readonly string[],
  nodes: ReadonlyMap<string, readonly Element[]>,
): readonly Element[] => anchorIds.flatMap((id) => [...(nodes.get(id) ?? [])])

/** Resolves the anchors' node elements and applies the anchor marker in one step —
 * returns the marked elements so the caller can center them in the viewport. */
export const markAnchorEntities = (
  anchorIds: readonly string[],
  nodes: ReadonlyMap<string, readonly Element[]>,
): readonly Element[] => {
  const anchorElems = resolveAnchorElements(anchorIds, nodes)
  applyAnchorMarker(anchorElems)
  return anchorElems
}

/** Anchor marker: a thick dashed halo ring cloned from the node's primary body shape and
 * inserted underneath it, plus `data-anchor` on the matched group. The halo is a SEPARATE
 * element rather than a stroke override on the body shape itself, so it composes with —
 * never fights — a `node_color` overlay, which owns the body shape's own stroke. Skips
 * groups already carrying a halo, so re-application never stacks rings. */
export const applyAnchorMarker = (elems: readonly Element[]): void => {
  for (const el of elems) {
    el.setAttribute('data-anchor', 'true')
    if (el.querySelector('[data-anchor-halo]')) continue
    // PlantUML emits the node's body shape as the group's first rect/polygon/path,
    // before any icon paths — halo only that one, not every decorative glyph.
    const body = shapeChildren(el)[0]
    if (!body?.parentNode) continue
    const halo = body.cloneNode(false) as SVGElement
    halo.setAttribute('data-anchor-halo', 'true')
    halo.removeAttribute('id')
    halo.style.setProperty('fill', 'none', 'important')
    halo.style.setProperty('stroke', ANCHOR_MARKER_COLOR, 'important')
    halo.style.setProperty('stroke-width', '6', 'important')
    halo.style.setProperty('stroke-dasharray', '8 4', 'important')
    halo.style.setProperty('pointer-events', 'none', 'important')
    body.parentNode.insertBefore(halo, body)
  }
}

export interface AnchorBadge {
  readonly id: string
  readonly name: string
}

/** Legend entries for the anchor badge row — resolves each anchor id to its entity name,
 * falling back to the raw id when the entity is absent from the returned population. */
export const anchorBadges = (
  anchorIds: readonly string[],
  entities: readonly EntityItemSummary[],
): readonly AnchorBadge[] => {
  const nameById = new Map(entities.map((entity) => [entity.id, entity.name]))
  return anchorIds.map((id) => ({ id, name: nameById.get(id) ?? id }))
}

/** Screen-space rectangle (`getBoundingClientRect` shape, structurally). */
export interface ScreenRect {
  readonly left: number
  readonly top: number
  readonly width: number
  readonly height: number
}

/** Smallest rect covering every input; `null` for an empty list. */
export const unionRect = (rects: readonly ScreenRect[]): ScreenRect | null => {
  if (rects.length === 0) return null
  const left = Math.min(...rects.map((r) => r.left))
  const top = Math.min(...rects.map((r) => r.top))
  const right = Math.max(...rects.map((r) => r.left + r.width))
  const bottom = Math.max(...rects.map((r) => r.top + r.height))
  return { left, top, width: right - left, height: bottom - top }
}

/** Screen-space translation moving `target`'s center onto `viewport`'s center. The pan/zoom
 * translate is applied outermost (before scale, origin 0 0), so screen pixels and translate
 * pixels coincide regardless of the current zoom — the delta adds straight onto `tx`/`ty`. */
export const centerDelta = (
  viewport: ScreenRect,
  target: ScreenRect,
): { readonly dx: number; readonly dy: number } => ({
  dx: viewport.left + viewport.width / 2 - (target.left + target.width / 2),
  dy: viewport.top + viewport.height / 2 - (target.top + target.height / 2),
})

/** Re-fits the diagram, then pans the anchors' union bounding box to the viewport center
 * via `panBy`. Awaiting `fit` first makes the sequence deterministic against the view's
 * own fit-on-render watcher (fitting is idempotent), and both rects are only measured
 * AFTER the fit so the screen-space delta reflects the final fitted transform. */
export const centerAnchorsAfterFit = async (
  anchorElems: readonly Element[],
  container: Element | null,
  fit: () => Promise<void>,
  panBy: (dx: number, dy: number) => void,
): Promise<void> => {
  if (anchorElems.length === 0 || container === null) return
  await fit()
  const target = unionRect(anchorElems.map((el) => el.getBoundingClientRect()))
  if (!target) return
  const { dx, dy } = centerDelta(container.getBoundingClientRect(), target)
  panBy(dx, dy)
}

/** Tags each derived connection's matched SVG elements with `data-certainty` — nothing
 * else reads the notation differently for a derived edge (PlantUML draws every connection
 * the same way regardless of provenance), so this is purely a hook for the sidebar's own
 * click handling and for tests to target a derived edge deterministically. */
export const markDerivedConnections = (
  edges: ReadonlyMap<string, readonly Element[]>,
  connections: readonly DiagramConnection[],
): void => {
  const certaintyByConnId = new Map(connections.filter((c) => c.certainty).map((c) => [c.artifact_id, c.certainty!]))
  for (const [connId, elems] of edges) {
    const certainty = certaintyByConnId.get(connId)
    if (!certainty) continue
    for (const el of elems) el.setAttribute('data-certainty', certainty)
  }
}

/** Applies the projection's node/edge highlight overlays plus derived/anchor markers onto a
 * freshly rendered diagram SVG, returning the anchor elements for post-fit centering. The
 * overlay is client-side only — the rendered notation is never mutated at the source. */
export const applyDiagramOverlay = (
  svgEl: SVGSVGElement,
  projectionItems: readonly ProjectedOccurrence[],
  diagramEntities: readonly DiagramContextEntity[],
  diagramConnections: readonly DiagramConnection[],
  anchorIds: readonly string[],
): readonly Element[] => {
  const entityStyleById = projectionByItemId(projectionItems)
  const { nodes, edges } = resolveElementMap('archimate-layered', svgEl, {
    entities: diagramEntities,
    connections: diagramConnections,
  })
  for (const [entityId, elems] of nodes) applyNodeColorOverlay(elems, entityStyleById.get(entityId)?.style.node_color)
  for (const [connId, elems] of edges) {
    const style = entityStyleById.get(connId)?.style
    applyEdgeHighlightOverlay(elems, style?.edge_color, style?.edge_emphasis)
  }
  markDerivedConnections(edges, diagramConnections)
  return markAnchorEntities(anchorIds, nodes)
}
