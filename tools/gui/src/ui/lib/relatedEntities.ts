import type { EntityContextConnection, EntityDisplayInfo } from '../../domain'

/** The far end of *conn* seen from *ownerId*, as a picker row — or undefined when the owner is neither end. */
const farEnd = (conn: EntityContextConnection, ownerId: string): EntityDisplayInfo | undefined => {
  const fromSource = ownerId === conn.source
  if (!fromSource && ownerId !== conn.target) return undefined
  const otherId = fromSource ? conn.target : conn.source
  const name = (fromSource ? conn.target_name : conn.source_name) ?? otherId
  const artifactType = fromSource ? conn.target_artifact_type : conn.source_artifact_type
  return {
    artifact_id: otherId,
    name,
    artifact_type: artifactType,
    domain: fromSource ? conn.target_domain : conn.source_domain,
    subdomain: '',
    status: fromSource ? conn.target_scope : conn.source_scope,
    display_alias: '',
    element_type: artifactType,
    element_label: name,
    diagram_internal: false,
  }
}

/**
 * What each owner relates to in the model that the diagram does not draw yet: per owner, the far ends of
 * its connections outside *drawn*, each once, by name. Every owner gets an entry, empty when it has none.
 */
export function relatedEntitiesOf(
  owners: readonly string[],
  drawn: ReadonlySet<string>,
  connections: Iterable<EntityContextConnection>,
): Record<string, EntityDisplayInfo[]> {
  const known = [...connections]
  const relatedTo = (ownerId: string): EntityDisplayInfo[] => {
    const ends = known
      .map((conn) => farEnd(conn, ownerId))
      .filter((end): end is EntityDisplayInfo => end !== undefined && !drawn.has(end.artifact_id))
    const firstOfEach = ends.filter((end, index) => ends.findIndex((e) => e.artifact_id === end.artifact_id) === index)
    return firstOfEach.sort((a, b) => a.name.localeCompare(b.name))
  }
  return Object.fromEntries(owners.map((ownerId) => [ownerId, relatedTo(ownerId)]))
}
