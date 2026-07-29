import type { C4Navigation, DiagramConnection, EntitySummary } from '../../domain'

/**
 * Build alias→artifactId map for SVG interactivity.
 *
 * Stores the raw alias, a PlantUML-safe variant (non-alphanumeric chars → '_'), and that
 * variant with a leading '_'. The leading-'_' form mirrors the class-diagram renderer's
 * `_safe_alias` ('_' + sanitised id), which guarantees a PlantUML-valid alias; without it,
 * class-diagram SVG nodes (whose `data-qualified-name` carries the '_'-prefixed alias)
 * would never resolve and so would not be selectable.
 */
export function buildAliasToId(entities: ReadonlyArray<EntitySummary>): Map<string, string> {
  const map = new Map<string, string>()
  for (const e of entities) {
    if (!e.display_alias) continue
    const safe = e.display_alias.replace(/[^a-zA-Z0-9_]/g, '_')
    for (const alias of [e.display_alias, safe, `_${safe}`]) {
      // First non-fragment id wins: prefer a canonical workspace id (CLF@…) over a
      // diagram-scoped '#fragment' id so the click target resolves to a loadable entity.
      const existing = map.get(alias)
      if (existing === undefined || (existing.includes('#') && !e.artifact_id.includes('#'))) {
        map.set(alias, e.artifact_id)
      }
    }
  }
  return map
}

/** True when the entity lives inside a diagram (no standalone file). */
export function isDiagramOnly(entity: { host_diagram_id?: string | null }): boolean {
  return !!entity.host_diagram_id
}

/** Matrix diagrams render their stored Markdown and must never call the SVG renderer. */
export function diagramNeedsSvg(diagramType: string | null | undefined): boolean {
  return !!diagramType && diagramType !== 'matrix'
}

/**
 * Builds a map of entityId → childDiagramId from the C4 navigation context.
 *
 * For L2→L3 children, the child carries its own scope_entity_id (the container
 * whose component diagram it is). For L1/L2 same-scope children, the child shares
 * the parent's scope entity — fall back to c4Nav.scope_entity_id.
 */
export function buildDrilldownByEntityId(
  c4Nav: C4Navigation | null | undefined,
): Record<string, string> {
  if (!c4Nav) return {}
  const map: Record<string, string> = {}
  for (const child of c4Nav.child_diagrams) {
    const entityId = child.scope_entity_id ?? c4Nav.scope_entity_id
    if (entityId) map[entityId] = child.diagram_id
  }
  return map
}

export type ConnectionAliasMap = {
  queue: Map<string, DiagramConnection[]>
  fallback: Map<string, DiagramConnection>
}

/**
 * Build bidirectional alias-keyed lookup structures for SVG edge interactivity.
 *
 * `queue` holds ordered lists of connections per forward/reverse key so that
 * parallel edges between the same pair of nodes are each matched at most once.
 * `fallback` holds the first connection seen per key for unordered lookups.
 */
export function buildConnectionAliasMap(
  connections: ReadonlyArray<DiagramConnection>,
): ConnectionAliasMap {
  const queue = new Map<string, DiagramConnection[]>()
  const fallback = new Map<string, DiagramConnection>()
  for (const conn of connections) {
    if (!conn.source_alias || !conn.target_alias) continue
    const fwd = `${conn.source_alias}:${conn.target_alias}`
    const rev = `${conn.target_alias}:${conn.source_alias}`
    const q = queue.get(fwd) ?? []
    q.push(conn)
    queue.set(fwd, q)
    fallback.set(fwd, conn)
    if (!fallback.has(rev)) fallback.set(rev, conn)
  }
  return { queue, fallback }
}

/**
 * Resolve which DiagramConnection corresponds to an SVG edge between aliases a1 and a2.
 * Consumes from the queue first (for parallel edges), then falls back to the first seen.
 */
export function resolveConnection(
  a1: string,
  a2: string,
  { queue, fallback }: ConnectionAliasMap,
): DiagramConnection | undefined {
  const fwd = `${a1}:${a2}`
  const rev = `${a2}:${a1}`
  return (
    queue.get(fwd)?.shift()
    ?? queue.get(rev)?.shift()
    ?? fallback.get(fwd)
    ?? fallback.get(rev)
  )
}
