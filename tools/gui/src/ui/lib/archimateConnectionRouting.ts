/**
 * Which drawings of its endpoints a connection's arrows run between.
 *
 * An entity may be drawn more than once. The model still holds one connection — A realizes B,
 * wherever either is drawn — so what varies per drawing is which boxes the arrow lands on. That is
 * diagram data, and it travels in `diagram-entities` under `_connections`, the same transport the
 * backend reads as `diagram-connections`.
 *
 * **One entry is one arrow.** No entry means one arrow between the base drawings, which is what
 * every diagram authored before any of this means, so nothing needs migrating.
 *
 * **The rule.** A connection may be drawn once per (source-drawing, target-drawing) pair, and each
 * drawing takes part in at most one instance of it. That is a matching, and it is what lets a
 * duplicated cluster read as a complete unit — A1→B1 in one copy, A2→B2 in the other — while
 * forbidding the cross-pairings (A1→B2, A2→B1) that repeat a fact without adding one. When an
 * endpoint is drawn only once the matching collapses to a single arrow, which is the older,
 * stricter behaviour: two arrows into the same box really is the same fact twice.
 */

export type Endpoint = 'source' | 'target'

/** Which drawing of an endpoint: null is the entity's base drawing, a string is an occurrence id. */
export type Drawing = string | null

export interface ConnectionInstance {
  artifact_id: string
  'source-occurrence'?: string
  'target-occurrence'?: string
  [key: string]: unknown
}

const OCCURRENCE_KEY: Record<Endpoint, 'source-occurrence' | 'target-occurrence'> = {
  source: 'source-occurrence',
  target: 'target-occurrence',
}

/** The per-arrow diagram entries, ignoring anything that is not one. */
export const routingItems = (diagramEntities: Record<string, unknown>): ConnectionInstance[] => {
  const raw = diagramEntities._connections
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is ConnectionInstance =>
    !!item && typeof item === 'object' && typeof (item as Record<string, unknown>).artifact_id === 'string',
  )
}

/** Which side of *conn* is *entityId*, or null when it is neither. */
export const endpointOf = (
  conn: { source: string, target: string },
  entityId: string,
): Endpoint | null =>
  conn.source === entityId ? 'source' : conn.target === entityId ? 'target' : null

const drawingIn = (instance: ConnectionInstance, endpoint: Endpoint): Drawing => {
  const value = instance[OCCURRENCE_KEY[endpoint]]
  return typeof value === 'string' && value ? value : null
}

/** Every arrow the diagram draws for *connectionId*. */
export const instancesOf = (
  diagramEntities: Record<string, unknown>,
  connectionId: string,
): ConnectionInstance[] => routingItems(diagramEntities).filter((item) => item.artifact_id === connectionId)

/**
 * Whether *drawing* already carries this connection on *endpoint*.
 *
 * With no entries at all the base drawings carry it, which keeps an unrouted diagram meaning what
 * it has always meant.
 */
export const drawingCarries = (
  diagramEntities: Record<string, unknown>,
  connectionId: string,
  endpoint: Endpoint,
  drawing: Drawing,
): boolean => {
  const instances = instancesOf(diagramEntities, connectionId)
  if (!instances.length) return drawing === null
  return instances.some((instance) => drawingIn(instance, endpoint) === drawing)
}

/** The entry without empty routing keys, or null when it would then say only its own id. */
const withoutEmptyRouting = (entry: ConnectionInstance): ConnectionInstance | null => {
  const { 'source-occurrence': source, 'target-occurrence': target, ...rest } = entry
  const kept: ConnectionInstance = { ...rest }
  if (source) kept['source-occurrence'] = source
  if (target) kept['target-occurrence'] = target
  return Object.keys(kept).length > 1 ? kept : null
}

const instanceEntry = (
  connectionId: string,
  pairing: Record<Endpoint, Drawing>,
  carried: Record<string, unknown>,
): ConnectionInstance => {
  const entry: ConnectionInstance = { ...carried, artifact_id: connectionId }
  if (pairing.source) entry['source-occurrence'] = pairing.source
  if (pairing.target) entry['target-occurrence'] = pairing.target
  return entry
}

/**
 * The drawing on the far side that this arrow should attach to.
 *
 * The first one not already carrying this connection, base first — so claiming a connection from a
 * duplicated cluster's second copy naturally pairs it with the other endpoint's second copy, and
 * the author never has to say so.
 */
export const freeDrawingOn = (
  diagramEntities: Record<string, unknown>,
  connectionId: string,
  endpoint: Endpoint,
  candidates: readonly Drawing[],
): Drawing | undefined =>
  candidates.find((candidate) => !drawingCarries(diagramEntities, connectionId, endpoint, candidate))

/**
 * Draw this connection between *drawing* and a free drawing on the other side.
 *
 * The label opt-ins already on the connection are carried onto the new arrow: they describe the
 * relation, not one picture of it.
 */
export const claimInstance = (
  diagramEntities: Record<string, unknown>,
  connectionId: string,
  endpoint: Endpoint,
  drawing: Drawing,
  otherDrawing: Drawing,
): Record<string, unknown> => {
  const existing = instancesOf(diagramEntities, connectionId)
  const carried = Object.fromEntries(
    Object.entries(existing[0] ?? {}).filter(
      ([key]) => key !== 'artifact_id' && key !== 'source-occurrence' && key !== 'target-occurrence',
    ),
  )
  const pairing: Record<Endpoint, Drawing> = endpoint === 'source'
    ? { source: drawing, target: otherDrawing }
    : { source: otherDrawing, target: drawing }
  const entry = instanceEntry(connectionId, pairing, carried)
  const already = existing.some(
    (item) => drawingIn(item, 'source') === pairing.source && drawingIn(item, 'target') === pairing.target,
  )
  if (already) return diagramEntities
  // The first arrow of a connection with no opt-ins between the base drawings is what an absent
  // entry already says, so it is left unwritten rather than stated redundantly.
  const kept = withoutEmptyRouting(entry)
  if (!existing.length && !kept) return diagramEntities
  return { ...diagramEntities, _connections: [...routingItems(diagramEntities), kept ?? entry] }
}

/**
 * Write down the base-to-base arrow an empty entry list leaves implicit.
 *
 * Needed before adding a second arrow: once any entry exists the implicit one stops counting, so
 * claiming a connection for a second drawing would otherwise *move* the first arrow rather than
 * add one.
 */
export const withBaseInstance = (
  diagramEntities: Record<string, unknown>,
  connectionId: string,
): Record<string, unknown> =>
  instancesOf(diagramEntities, connectionId).length
    ? diagramEntities
    : { ...diagramEntities, _connections: [...routingItems(diagramEntities), { artifact_id: connectionId }] }

/** Stop drawing this connection at *drawing*; other arrows for it stay. */
export const releaseInstance = (
  diagramEntities: Record<string, unknown>,
  connectionId: string,
  endpoint: Endpoint,
  drawing: Drawing,
): Record<string, unknown> => ({
  ...diagramEntities,
  _connections: routingItems(diagramEntities).filter(
    (item) => item.artifact_id !== connectionId || drawingIn(item, endpoint) !== drawing,
  ),
})

/** Stop drawing this connection anywhere. */
export const releaseConnection = (
  diagramEntities: Record<string, unknown>,
  connectionId: string,
): Record<string, unknown> => ({
  ...diagramEntities,
  _connections: routingItems(diagramEntities).filter((item) => item.artifact_id !== connectionId),
})

/**
 * Forget everything a diagram said about an entity it no longer draws.
 *
 * Removing an entity used to leave its extra drawings behind — the panel kept listing rows for an
 * entity the diagram no longer contained — and would now leave arrows pointing at occurrence ids
 * nothing declares.
 */
export const forgetEntity = (
  diagramEntities: Record<string, unknown>,
  entityId: string,
  connectionsTouchingEntity: readonly string[],
): Record<string, unknown> => {
  const occurrences = Array.isArray(diagramEntities.occurrence) ? diagramEntities.occurrence : []
  const dropped = new Set(
    occurrences
      .filter((item): item is { id: string, backing_entity_id: string } =>
        !!item && typeof item === 'object'
        && (item as Record<string, unknown>).backing_entity_id === entityId,
      )
      .map((item) => item.id),
  )
  const orphaned = new Set(connectionsTouchingEntity)
  return {
    ...diagramEntities,
    occurrence: occurrences.filter((item) =>
      !(!!item && typeof item === 'object' && dropped.has((item as { id?: string }).id ?? '')),
    ),
    _connections: routingItems(diagramEntities)
      // An arrow that ran to a drawing that is gone is gone with it; one that never did survives.
      .filter((item) => !orphaned.has(item.artifact_id))
      .filter((item) => !dropped.has(item['source-occurrence'] ?? '') && !dropped.has(item['target-occurrence'] ?? ''))
      .map(withoutEmptyRouting)
      .filter((item): item is ConnectionInstance => item !== null),
  }
}

/** Every occurrence id the diagram no longer declares, so a caller can tell stale routing exists. */
export const routedOccurrenceIds = (diagramEntities: Record<string, unknown>): Set<string> => {
  const ids = new Set<string>()
  for (const item of routingItems(diagramEntities)) {
    for (const endpoint of ['source', 'target'] as const) {
      const drawing = drawingIn(item, endpoint)
      if (drawing) ids.add(drawing)
    }
  }
  return ids
}
