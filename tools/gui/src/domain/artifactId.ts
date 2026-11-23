/**
 * Artifact identity, client side.
 *
 * Mirrors the backend's `src/domain/artifact_id.py`: an artifact id is
 * `PREFIX@epoch.random[.slug]`, where the slug is a human-readable hint and identity is the
 * `PREFIX@epoch.random` stem. A connection id composes two of them as
 * `source---target@@connection-type`.
 *
 * The client needs this because the two forms meet here. A diagram's stored
 * `connection_ids_used` names endpoints in full, as authored; the connection records the API
 * returns name them by stem. Joining those two sets by string equality matches nothing, and
 * nothing reports it — the join simply yields fewer connections than it should.
 */

const SLUG_TAIL = /^([A-Za-z]{2,6}@\d+\.[A-Za-z0-9_-]+)\.[A-Za-z0-9][A-Za-z0-9-]*$/

/** The rename-stable stem of an entity id; anything not entity-shaped is returned as-is. */
export const stableEntityId = (id: string): string => SLUG_TAIL.exec(id)?.[1] ?? id

/**
 * A connection id with both endpoints reduced to their stems.
 *
 * Split on the *last* `@@` and the first `---`, so a connection type containing neither is
 * safe. Anything not connection-shaped is returned unchanged rather than mangled.
 */
export const stableConnectionId = (id: string): string => {
  const parts = connectionParts(id)
  return parts ? `${stableEntityId(parts.source)}---${stableEntityId(parts.target)}@@${parts.type}` : id
}

/** The id of the connection of *type* from *source* to *target*. */
export const connectionId = (source: string, type: string, target: string): string => `${source}---${target}@@${type}`

/** A connection id's source, type and target as written; null where *id* is not connection-shaped. */
export const connectionParts = (
  id: string,
): { readonly source: string; readonly type: string; readonly target: string } | null => {
  const typeAt = id.lastIndexOf('@@')
  const joinAt = typeAt < 0 ? -1 : id.slice(0, typeAt).indexOf('---')
  return joinAt < 0 ? null
    : { source: id.slice(0, joinAt), type: id.slice(typeAt + 2), target: id.slice(joinAt + 3, typeAt) }
}

/** Whether *id* is an entity id (`PREFIX@epoch.random[.slug]`) rather than another kind of reference. */
const ENTITY_ID = /^[A-Za-z]{2,6}@\d+\.[A-Za-z0-9_-]+(\.[A-Za-z0-9][A-Za-z0-9-]*)?$/
export const isEntityId = (id: string): boolean => ENTITY_ID.test(id)
