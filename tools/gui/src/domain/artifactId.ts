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

const SLUG_TAIL = /^([A-Za-z]{2,6}@\d+\.[A-Za-z0-9-]+)\.[A-Za-z0-9][A-Za-z0-9-]*$/

/** The rename-stable stem of an entity id; anything not entity-shaped is returned as-is. */
export const stableEntityId = (id: string): string => SLUG_TAIL.exec(id)?.[1] ?? id

/**
 * A connection id with both endpoints reduced to their stems.
 *
 * Split on the *last* `@@` and the first `---`, so a connection type containing neither is
 * safe. Anything not connection-shaped is returned unchanged rather than mangled.
 */
export const stableConnectionId = (id: string): string => {
  const typeAt = id.lastIndexOf('@@')
  if (typeAt < 0) return id
  const endpoints = id.slice(0, typeAt)
  const connectionType = id.slice(typeAt + 2)
  const joinAt = endpoints.indexOf('---')
  if (joinAt < 0) return id
  const source = stableEntityId(endpoints.slice(0, joinAt))
  const target = stableEntityId(endpoints.slice(joinAt + 3))
  return `${source}---${target}@@${connectionType}`
}
