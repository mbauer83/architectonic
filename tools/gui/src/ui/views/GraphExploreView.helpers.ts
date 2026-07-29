/**
 * Pure helpers for the viewpoint-driven exploration mode: `group_by` -> cluster key
 * resolution, style-token -> node/edge visual mapping layered on top of
 * `viewpointStyleTokens.ts`'s fixed vocabulary, and anchored-execution derivations
 * (hop distances, layout choice, distance coloring).
 */

import type {
  ConnectionItemSummary, EntityItemSummary, ProjectedOccurrence, ViewpointDefinitionEnvelope, ViewpointProjection,
} from '../../domain'
import type { StyleValue } from '../../domain/schemas/viewpoints'
import { resolveStyleColor, styleTokenString, tokenShape, tokenIconLetter, tokenEdgeEmphasis } from '../lib/viewpointStyleTokens'
import { archimateGlyphMarkup } from '../lib/glyphKey'
import type { EdgeEndMarker, EdgeVisual, NodeVisual } from '../components/GraphCanvas.helpers'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import { executionRouteFor } from './ViewpointsManagementView.helpers'
import { DOMAIN_NAMES } from '../../domain/types.generated'
import type { BandPlacement } from '../composables/useForceGraphLayout'

/** The in-page viewpoint selector executes exploration-representation definitions
 * in place; anything else (table/matrix/diagram) must redirect to its own dedicated
 * surface instead of being force-rendered as a graph, which is how it declared its
 * intended presentation. `null` means "stay here and execute as exploration". */
export const explorationRedirectFor = (
  envelope: ViewpointDefinitionEnvelope | undefined,
): { path: string; query: { viewpoint: string } } | null => {
  if (!envelope) return null
  const representation = presentationFromMapping(envelope.presentation)?.representation ?? 'exploration'
  return representation === 'exploration' ? null : executionRouteFor(envelope)
}

/** Same shape as `EditDiagramView.helpers.ts`'s function of the same name — kept as a
 * small local duplicate rather than a cross-view import so this view's helper module has
 * no dependency on another view's already-shipped module. */
export const projectionByItemId = (projection: ViewpointProjection | null): ReadonlyMap<string, ProjectedOccurrence> =>
  new Map((projection?.items ?? []).map((item) => [item.item_id, item]))

/** `GraphEdge` (a rendered force-graph edge) is keyed by source/target/connType, not the
 * underlying connection's artifact id — this derives the matching key so a connection's
 * style (looked up by id via `projectionByItemId`) can be joined back onto it. */
export const edgeStyleKey = (source: string, target: string, connType: string): string => `${source}|${target}|${connType}`

export const buildConnectionStyleIndex = (
  connections: readonly ConnectionItemSummary[],
  projection: ViewpointProjection | null,
): ReadonlyMap<string, Readonly<Record<string, StyleValue>>> => {
  const byId = projectionByItemId(projection)
  const index = new Map<string, Readonly<Record<string, StyleValue>>>()
  for (const connection of connections) {
    const item = byId.get(connection.id)
    if (item) index.set(edgeStyleKey(connection.source, connection.target, connection.type), item.style)
  }
  return index
}

/** Execution connection summaries joined onto rendered edges by the same
 * source/target/connType key `buildConnectionStyleIndex` uses — this is how a selected
 * edge finds its provenance (certainty, hops, ordered witness steps). */
export const buildConnectionSummaryIndex = (
  connections: readonly ConnectionItemSummary[],
): ReadonlyMap<string, ConnectionItemSummary> => {
  const index = new Map<string, ConnectionItemSummary>()
  for (const connection of connections) {
    index.set(edgeStyleKey(connection.source, connection.target, connection.type), connection)
  }
  return index
}

/** Human-readable name derived from an artifact id's slug part — used where the real
 * display name is not in the result (e.g. witness-chain intermediates). */
export const friendlyEntityName = (id: string): string => {
  const parts = id.split('.')
  return parts.length > 2 ? parts.slice(2).join(' ').replace(/-/g, ' ') : id
}

/** `group_by` resolves against the fixed entity summary — the three well-known
 * non-attribute dimensions are always resolvable; an arbitrary profile-attribute path is
 * not (the summary carries no properties map), so it falls back to grouping by type
 * rather than silently mis-grouping. */
export const groupKeyFor = (
  entity: Pick<EntityItemSummary, 'type' | 'group' | 'specialization_slugs' | 'domain'>,
  groupBy: string | null,
): string => {
  if (groupBy === 'group') return entity.group
  if (groupBy === 'specialization') return entity.specialization_slugs[0] ?? '(none)'
  // `domain` is a declared dimension, so it must be resolved here. Falling through to the
  // type default would group by something the definition did not ask for, and — because the
  // keys would then not be domains — silently disable the layered ordering that grouping by
  // domain exists to enable.
  if (groupBy === 'domain') return entity.domain || 'unknown'
  return entity.type
}

/** `node_color`/`node_shape`/`node_icon` resolved from the projection's per-entity style
 * map, falling back to the existing domain-color convention when the viewpoint carries
 * no styling for a given capability. `node_color` alone can be a scale-mode
 * `{position, tokens}` value (interpolated); shape/icon always read a discrete token. */
export const nodeVisualFor = (
  style: Readonly<Record<string, StyleValue>> | undefined,
  fallbackColor: string,
  artifactType?: string,
): NodeVisual => ({
  color: style?.node_color !== undefined ? resolveStyleColor(style.node_color) : fallbackColor,
  shape: style?.node_shape !== undefined ? tokenShape(styleTokenString(style.node_shape)) : 'circle',
  iconLetter: style?.node_icon !== undefined ? tokenIconLetter(styleTokenString(style.node_icon)) : null,
  glyph: archimateGlyphMarkup(artifactType),
})

/** Anchor-relative modeled distances as the execution reported them
 * (`anchor_modeled_distance`: 0 = anchor, 1 = direct modeled edge, N = minimum derived
 * witness-chain length). Entities the server left unranked are absent from the map —
 * "no distance" is its own visual category, never rendered as 0 or 1. */
export const anchorDistancesFromResult = (
  entities: readonly { id: string; anchor_modeled_distance?: number | null }[],
): Map<string, number> => {
  const distances = new Map<string, number>()
  for (const entity of entities) {
    if (entity.anchor_modeled_distance != null) distances.set(entity.id, entity.anchor_modeled_distance)
  }
  return distances
}

export type ExplorationLayoutChoice = 'clusters' | 'radial' | 'force'
export type ExplorationLayoutOverride = ExplorationLayoutChoice | 'auto'

const EXPLORATION_LAYOUT_VALUES: readonly ExplorationLayoutChoice[] = ['clusters', 'radial', 'force']

/** Which layout the exploration surface should apply for the current execution: an
 * explicit in-session user override always wins; otherwise the definition's validated
 * `display_options.layout` (an unknown/absent value is ignored, not an error); otherwise
 * an anchored execution defaults to the anchor-centric radial layout and an unanchored
 * one to the `group_by` cluster packing. */
export const effectiveExplorationLayout = (
  override: ExplorationLayoutOverride,
  displayOptionLayout: unknown,
  anchored: boolean,
): ExplorationLayoutChoice => {
  if (override !== 'auto') return override
  const declared = EXPLORATION_LAYOUT_VALUES.find((value) => value === displayOptionLayout)
  if (declared) return declared
  return anchored ? 'radial' : 'clusters'
}

export type ExplorationFill = 'domain' | 'hop-distance'

/**
 * What unstyled exploration nodes are filled by.
 *
 * Declared by the presentation, never inferred from the query. An anchored query is a
 * statement about reachability — "start here and walk" — not a request to recolour the
 * graph; taking a parameter should not silently change how a view looks.
 *
 * Falls back to domain colouring when there is no distance range to express. With every
 * neighbour one hop away, a distance spectrum paints every node the same colour and
 * replaces the one distinction that still carries meaning at that size — which layer each
 * element belongs to.
 */
export const effectiveExplorationFill = (
  displayOptionColorBy: unknown,
  maxHopDepth: number,
): ExplorationFill =>
  displayOptionColorBy === 'hop-distance' && maxHopDepth > 1 ? 'hop-distance' : 'domain'

/** Hop-distance fill for nodes the projection leaves uncolored: the same
 * `heat-near`→`heat-far` spectrum scale-mode style rules use, so distance reads
 * consistently across surfaces. Depth 0 (the anchor itself) is the near endpoint. */
export const distanceColor = (depth: number, maxDepth: number): string =>
  resolveStyleColor({ position: maxDepth > 0 ? depth / maxDepth : 0, tokens: ['heat-near', 'heat-far'] })

export interface DistanceLegendEntry {
  readonly label: string
  readonly color: string
}

/** One legend chip per OBSERVED nonzero modeled distance (the real ring set — e.g.
 * 1/2/4 when those are the witness-chain lengths present), colored exactly as
 * `distanceColor` colors the nodes. Distance 0 is the anchor itself, which the legend
 * already names with its dedicated Anchor chip. */
export const distanceLegend = (depths: readonly number[]): readonly DistanceLegendEntry[] => {
  const observed = [...new Set(depths.filter((depth) => depth > 0))].sort((a, b) => a - b)
  const maxDepth = observed.length > 0 ? observed[observed.length - 1] : 0
  return observed.map((depth) => ({
    label: depth === 1 ? '1 hop' : `${depth} hops`,
    color: distanceColor(depth, maxDepth),
  }))
}

/**
 * How one relationship type is drawn, as served by `/api/relation-notations`.
 *
 * Mirrors the ontology's own `notation:` declaration — the shapes are structural, so this type
 * names no relationship and the generic canvas can consume it unchanged. The architecture
 * surface owns the *lookup* (connection type → notation); the canvas owns the drawing.
 */
export interface RelationNotation {
  line: 'solid' | 'dashed' | 'dotted'
  source: EdgeEndMarker
  target: EdgeEndMarker
}

/** Fetch every relationship type's notation. One request per surface, not per edge. */
export const fetchRelationNotations = async (): Promise<ReadonlyMap<string, RelationNotation>> => {
  const response = await fetch('/api/relation-notations')
  if (!response.ok) return new Map()
  const body = await response.json() as { notations?: Record<string, RelationNotation> }
  return new Map(Object.entries(body.notations ?? {}))
}

/** Provenance dash patterns: derived edges are visually distinct from modeled ones by
 * construction, and certain vs potential derivations differ in dash density. The edge
 * legend labels exactly these patterns. */
export const DERIVED_EDGE_DASH: Readonly<Record<'certain' | 'potential', string>> = {
  certain: '7 4',
  potential: '2 4',
}

/** `edge_color`/`edge_emphasis` resolved from the projection's per-connection style map;
 * `null` fields mean "no viewpoint style — render the default edge". A derived
 * connection with no authored emphasis falls back to its provenance dash so modeled and
 * derived edges never look identical. */
export const edgeVisualFor = (
  style: Readonly<Record<string, StyleValue>> | undefined,
  certainty: 'certain' | 'potential' | null = null,
  notation?: RelationNotation,
): EdgeVisual => {
  const emphasis = style?.edge_emphasis !== undefined ? tokenEdgeEmphasis(styleTokenString(style.edge_emphasis)) : null
  return {
    stroke: style?.edge_color !== undefined ? resolveStyleColor(style.edge_color) : null,
    strokeWidth: emphasis?.strokeWidth ?? null,
    // Precedence: an explicit viewpoint emphasis, then derivation provenance, then the
    // relationship's own notation. A viewpoint that styles an edge is making a deliberate
    // statement about *this view* and outranks the notation; provenance outranks it too,
    // because "this edge was inferred" is not something the relationship type can say.
    dashArray: emphasis?.dashArray
      ?? (certainty !== null ? DERIVED_EDGE_DASH[certainty] : notationDash(notation)),
    sourceMarker: notation?.source ?? 'none',
    targetMarker: notation?.target ?? 'filled-arrow',
  }
}

/** Line style from the ontology, as an SVG dash pattern. Solid is the absence of one. */
const notationDash = (notation: RelationNotation | undefined): string | undefined => {
  if (notation === undefined) return undefined
  if (notation.line === 'dashed') return '6 4'
  if (notation.line === 'dotted') return '2 3'
  return undefined
}

/** Static UI option tables for the exploration surface. */
export const EXPLORATION_LAYOUT_OPTIONS: { value: ExplorationLayoutOverride; label: string }[] = [
  { value: 'auto', label: 'Auto' }, { value: 'clusters', label: 'Clusters' },
  { value: 'radial', label: 'Radial' }, { value: 'force', label: 'Force' },
]

/**
 * Domains the layered ordering lifts out of the realization stack.
 *
 * Common holds elements the core layers share, and Implementation describes the work that
 * delivers them rather than a layer of the architecture; stacking either would assert a
 * realization ordering that does not exist. Everything else keeps the ontology's own
 * declared order, so a new domain from a plugged-in module falls into place without being
 * named here — `DOMAIN_NAMES` is generated from the module registry.
 */
const SIDE_DOMAINS: Record<string, 'left' | 'right'> = { common: 'left', implementation: 'right' }

/** True when every grouping key is an ontology domain, so the layered ordering applies. */
export const isDomainGrouping = (keys: readonly string[]): boolean =>
  keys.length > 0 && keys.every((key) => (DOMAIN_NAMES as readonly string[]).includes(key))

/**
 * Band and side for a domain, from the ontology's declared domain order.
 *
 * Position then means what it means in a layered view: intent above, realization
 * descending. Side domains borrow the band of the layer they sit beside so they land
 * level with the middle of the stack rather than above or below it.
 */
export const domainBandPlacement = (key: string): BandPlacement => {
  const side = SIDE_DOMAINS[key] ?? null
  if (side !== null) return { band: MIDDLE_CORE_BAND, side }
  const index = (DOMAIN_NAMES as readonly string[]).indexOf(key)
  return { band: index === -1 ? Number.MAX_SAFE_INTEGER : index, side: null }
}

/** The band side domains align with: the middle of the stacked (non-side) domains. */
const MIDDLE_CORE_BAND = Math.floor(
  (DOMAIN_NAMES as readonly string[]).filter((name) => !(name in SIDE_DOMAINS)).length / 2,
)

export const DOMAIN_COLORS: Record<string, string> = {
  motivation: '#d8c1e4', strategy: '#efbd5d', business: '#f4de7f',
  common: '#e8e5d3', application: '#b6d7e1', technology: '#c3e1b4',
}

/**
 * Hop distance from the entity the exploration opened on, by the parentage the walk recorded.
 *
 * Free exploration grows one hop at a time and remembers which node's expansion introduced
 * each other node (`addedBy`), so depth in that chain *is* distance from the root. A viewpoint
 * execution gets the same numbers from the server; this is the free-exploration counterpart,
 * and it is what makes the radial layout meaningful here at all — radial rings nodes around an
 * anchor, and until the root was treated as one this surface had no anchor to ring around.
 *
 * Breadth-first from the root rather than by walking each node's chain upward: a node whose
 * introducer has since been collapsed away has no route to the root, and simply gets no entry
 * — which `layoutRadialByDistance` already renders on its outermost ring.
 */
export const hopDepthByParentage = (
  nodes: readonly { id: string; addedBy?: string }[],
  rootId: string,
): ReadonlyMap<string, number> => {
  const children = new Map<string, string[]>()
  for (const node of nodes) {
    if (node.addedBy === undefined) continue
    const siblings = children.get(node.addedBy)
    if (siblings) siblings.push(node.id)
    else children.set(node.addedBy, [node.id])
  }
  const depth = new Map<string, number>([[rootId, 0]])
  const queue: string[] = [rootId]
  while (queue.length > 0) {
    const id = queue.shift()!
    for (const child of children.get(id) ?? []) {
      if (depth.has(child)) continue
      depth.set(child, depth.get(id)! + 1)
      queue.push(child)
    }
  }
  return depth
}
