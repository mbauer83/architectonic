import type { DiagramConnection, EntitySummary } from '../../domain'
import {
  buildAliasToId,
  buildConnectionAliasMap,
  resolveConnection,
} from '../views/DiagramDetailView.helpers'
import { occurrenceItems } from './archimateOccurrences'
import type { DiagramElementMap, DiagramMapContext } from './diagramViewerExtensions'

const pushInto = (map: Map<string, Element[]>, key: string, el: Element): void => {
  const list = map.get(key)
  if (list) list.push(el)
  else map.set(key, [el])
}

/** Resolve an SVG `g`'s matched alias from graphviz/PlantUML's known id/attribute conventions. */
const resolveNodeAlias = (g: SVGGElement, aliasToId: ReadonlyMap<string, string>): string | null => {
  const de = g.getAttribute('data-entity')
  if (de && aliasToId.has(de)) return de
  if (g.id.startsWith('entity_') && aliasToId.has(g.id.slice(7))) return g.id.slice(7)
  if (g.id && aliasToId.has(g.id)) return g.id
  const title = g.querySelector(':scope > title')?.textContent?.trim() ?? ''
  if (aliasToId.has(title)) return title
  if (g.id.startsWith('cluster_') && aliasToId.has(g.id.slice(8))) return g.id.slice(8)
  const qn = g.getAttribute('data-qualified-name') ?? ''
  if (qn) {
    const last = qn.split('.').pop() ?? ''
    if (last && aliasToId.has(last)) return last
  }
  return null
}

const mapNodes = (
  svgRoot: SVGSVGElement,
  entities: ReadonlyArray<EntitySummary>,
  diagramEntities?: Record<string, unknown>,
): { nodes: Map<string, Element[]>; svgNodeIdToAlias: Map<string, string> } => {
  const nodes = new Map<string, Element[]>()
  const svgNodeIdToAlias = new Map<string, string>()
  const aliasToId = buildAliasToId(entities)
  addOccurrenceAliases(aliasToId, entities, diagramEntities)
  if (!aliasToId.size) return { nodes, svgNodeIdToAlias }

  for (const g of Array.from(svgRoot.querySelectorAll<SVGGElement>('g'))) {
    const alias = resolveNodeAlias(g, aliasToId)
    if (!alias) continue
    const artifactId = aliasToId.get(alias)!
    if (g.id) svgNodeIdToAlias.set(g.id, alias)
    pushInto(nodes, artifactId, g)
  }
  return { nodes, svgNodeIdToAlias }
}

const addOccurrenceAliases = (
  aliasToId: Map<string, string>,
  entities: ReadonlyArray<EntitySummary>,
  diagramEntities?: Record<string, unknown>,
): void => {
  if (!diagramEntities) return
  const entityById = new Map(entities.map((entity) => [entity.artifact_id, entity]))
  const counts = new Map<string, number>()
  for (const occurrence of occurrenceItems(diagramEntities)) {
    const entity = entityById.get(occurrence.backing_entity_id)
    if (!entity?.display_alias) continue
    const base = entity.display_alias.replace(/[^a-zA-Z0-9_]/g, '_')
    const index = (counts.get(entity.artifact_id) ?? 1) + 1
    counts.set(entity.artifact_id, index)
    aliasToId.set(`${base}__${index}`, entity.artifact_id)
  }
}

const mapEdges = (
  svgRoot: SVGSVGElement,
  connections: ReadonlyArray<DiagramConnection>,
  svgNodeIdToAlias: ReadonlyMap<string, string>,
): Map<string, Element[]> => {
  const edges = new Map<string, Element[]>()
  const seenGroups = new Set<SVGGElement>()
  const addEdgeGroup = (g: SVGGElement, conn: DiagramConnection): void => {
    if (seenGroups.has(g)) return
    seenGroups.add(g)
    pushInto(edges, conn.artifact_id, g)
  }

  const connAliasMap = buildConnectionAliasMap(connections)

  // Primary: attribute-based (old PlantUML: data-entity-1/2 hold aliases or node ids)
  for (const g of Array.from(svgRoot.querySelectorAll<SVGGElement>('g[data-entity-1]'))) {
    const a1raw = g.getAttribute('data-entity-1') ?? ''
    const a2raw = g.getAttribute('data-entity-2') ?? ''
    const a1 = svgNodeIdToAlias.get(a1raw) ?? a1raw
    const a2 = svgNodeIdToAlias.get(a2raw) ?? a2raw
    const conn = resolveConnection(a1, a2, connAliasMap)
    if (conn) addEdgeGroup(g, conn)
  }

  // Fallback: id-based lookup via PlantUML's link_SOURCE_TARGET convention (old)
  // and SOURCE-TARGET path id convention (new PlantUML 1.2026+)
  for (const conn of connections) {
    if (!conn.source_alias || !conn.target_alias) continue
    const fwdId = `link_${conn.source_alias}_${conn.target_alias}`
    const revId = `link_${conn.target_alias}_${conn.source_alias}`
    let g = (svgRoot.getElementById(fwdId) ?? svgRoot.getElementById(revId)) as SVGGElement | null
    if (g) { addEdgeGroup(g, conn); continue }
    const pathFwd = svgRoot.getElementById(`${conn.source_alias}-${conn.target_alias}`)
    const pathRev = svgRoot.getElementById(`${conn.target_alias}-${conn.source_alias}`)
    g = (pathFwd ?? pathRev)?.closest('g') ?? null
    if (g) addEdgeGroup(g, conn)
  }
  return edges
}

/**
 * Default `mapElements` implementation for diagram types with no viewer extension of their
 * own: matches graphviz/PlantUML's SVG id/attribute conventions (the logic every renderer but
 * GSN/datatype relies on implicitly). One node or connection may match more than one SVG
 * element (WU-B3 multi-occurrence views); this only happens today if a renderer emits the same
 * alias twice, which none currently do — the one-to-many shape is forward-compatible, not yet
 * exercised by ArchiMate occurrence aliases such as `APP_A__2`.
 */
export function graphvizMapElements(svgRoot: SVGSVGElement, ctx: DiagramMapContext): DiagramElementMap {
  const { nodes, svgNodeIdToAlias } = mapNodes(svgRoot, ctx.entities, ctx.diagramEntities)
  const edges = mapEdges(svgRoot, ctx.connections, svgNodeIdToAlias)
  return { nodes, edges }
}
