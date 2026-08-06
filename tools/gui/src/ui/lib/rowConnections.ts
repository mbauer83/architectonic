import type { EntityContextConnection } from '../../domain'
import { drawingCarries, endpointOf, freeDrawingOn, type Drawing } from './archimateConnectionRouting'
import { occurrencesOf } from './archimateOccurrences'

export interface ConnEntry {
  conn: EntityContextConnection
  direction: 'out' | 'in'
  otherName: string
}

export interface ConnTypeGroup {
  included: ConnEntry[]
  excluded: ConnEntry[]
}

/**
 * The connections one *drawing* of an entity offers, grouped by connection type.
 *
 * A drawing shows a connection as included when it is the drawing carrying it. It offers one it
 * does not carry only while the far endpoint still has a drawing free to pair with — that is the
 * matching rule made visible: a duplicated cluster can draw its internal relation in each copy, so
 * each copy reads as a complete unit, while an endpoint drawn once cannot collect two arrows saying
 * the same thing.
 *
 * Both endpoints must be in the diagram: a connection to something not drawn is not a connection
 * anyone can see.
 */
export const connectionsByType = (options: {
  entityId: string
  drawing: Drawing
  candidates: readonly EntityContextConnection[]
  includedEntityIds: ReadonlySet<string>
  includedConnectionIds: ReadonlySet<string>
  diagramEntities: Record<string, unknown>
  nameOf: (entityId: string) => string | undefined
}): Array<[string, ConnTypeGroup]> => {
  const { entityId, drawing, candidates, includedEntityIds, includedConnectionIds } = options
  const { diagramEntities, nameOf } = options
  if (!includedEntityIds.has(entityId)) return []
  const byType = new Map<string, ConnTypeGroup>()
  for (const conn of candidates) {
    const endpoint = endpointOf(conn, entityId)
    if (!endpoint) continue
    if (!includedEntityIds.has(conn.source) || !includedEntityIds.has(conn.target)) continue
    const isOut = endpoint === 'source'
    const otherId = isOut ? conn.target : conn.source
    const included = includedConnectionIds.has(conn.artifact_id)
    const carriesIt = included && drawingCarries(diagramEntities, conn.artifact_id, endpoint, drawing)
    if (included && !carriesIt) {
      const otherEnd = isOut ? 'target' : 'source'
      const otherDrawings: Drawing[] = [null, ...occurrencesOf(diagramEntities, otherId).map((o) => o.id)]
      // Nothing free on the far side means there is no arrow to add, so offering it would be
      // offering a click that does nothing.
      if (freeDrawingOn(diagramEntities, conn.artifact_id, otherEnd, otherDrawings) === undefined) continue
    }
    const entry: ConnEntry = {
      conn,
      direction: isOut ? 'out' : 'in',
      otherName: nameOf(otherId) ?? conn.source_name ?? conn.target_name ?? otherId,
    }
    if (!byType.has(conn.conn_type)) byType.set(conn.conn_type, { included: [], excluded: [] })
    const bucket = byType.get(conn.conn_type)!
    if (carriesIt) bucket.included.push(entry)
    else bucket.excluded.push(entry)
  }
  return [...byType.entries()]
}
