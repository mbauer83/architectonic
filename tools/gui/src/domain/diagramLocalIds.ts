/**
 * The identifier grammar for a construct a diagram owns.
 *
 * A GSN goal, a swimlane, a lifeline — something drawn inside a diagram that has no file of its own.
 * Its identifier is composite: `{diagramId}#{entityType}/{localId}`, e.g.
 * `GSN@1781338120.3U4cRc.assurance-case#nodes/g11`. The server forms it in
 * `_diagram_entity_extraction.py`; this is the reader.
 *
 * Why the grammar has to be *parsed* rather than passed through: the local part contains a slash, and
 * a slash in a URL path ends the segment. Percent-encoding does not save it — the server decodes
 * `%2F` back before routing, so `/api/entities/GSN@…%23nodes%2Fg11` matches no route and answers 404.
 * These constructs are therefore addressed as what they are, sub-entities of their diagram:
 * `/api/diagrams/{diagramId}/entities/{entityType}/{localId}`, one segment per part, no slash inside
 * any of them.
 *
 * Parsing lives in the domain — beside the repository-link parsing in `artifactLinks` — because it is
 * a fact about identifiers, not about HTTP. Choosing the address from it is the adapter's job.
 */

/** The parts of a diagram-local identifier. */
export type DiagramLocalId = {
  /** The host diagram's own artifact id. */
  readonly diagramId: string
  /** The kind of construct, as the diagram type names it (`nodes`, `lanes`, …). */
  readonly entityType: string
  /** The construct's identifier within its diagram. */
  readonly localId: string
}

/**
 * The parts of `id` if it names a diagram-owned construct, else `null`.
 *
 * Returns `null` for an ordinary artifact id, and also for a malformed composite one — an id with a
 * `#` but no `type/local` after it is not a construct address, and guessing at one would send a
 * request that cannot be answered. Neither separator may appear inside the local id: an extra one
 * means a grammar this reader does not know, and addressing it anyway would request the wrong thing.
 */
export const parseDiagramLocalId = (id: string): DiagramLocalId | null => {
  const hash = id.indexOf('#')
  if (hash <= 0) return null
  const diagramId = id.slice(0, hash)
  const local = id.slice(hash + 1)
  const slash = local.indexOf('/')
  if (slash <= 0 || slash === local.length - 1) return null
  const entityType = local.slice(0, slash)
  const localId = local.slice(slash + 1)
  // A further slash or hash would mean the grammar has a part this reader does not know about.
  // Refusing is better than silently addressing the wrong construct, and it keeps the two
  // separators symmetric: neither may appear inside the local id.
  if (localId.includes('/') || localId.includes('#')) return null
  return { diagramId, entityType, localId }
}
