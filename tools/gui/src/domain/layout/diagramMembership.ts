/**
 * A diagram's membership without some of its entities: what a diagram write states once elements are
 * removed from the diagram (never from the model). The entities go from `entity_ids`, from every
 * grouping that lists them, and every connection with either end among them goes from
 * `connection_ids` — a connection id is `<source>---<target>@@<type>`.
 *
 * Ids are compared by their stable part (`stableEntityId`): a layout names an entity by its stable
 * id, while a diagram's lists may spell it with its slug.
 */
import type { AuthoredGrouping } from '../authoredGrouping'
import type { PictureContext } from '../schemas/diagrams'
import { stableEntityId } from '../artifactId'

export interface Membership {
  readonly entity_ids: readonly string[]
  readonly connection_ids: readonly string[]
  readonly authored_groupings?: readonly AuthoredGrouping[]
}

/** What a diagram draws, as last read: what a membership write starts from and sends back. */
export interface DrawnMembership extends Membership {
  readonly diagram_type: string
  readonly name: string
  readonly diagram_entities?: Readonly<Record<string, unknown>>
}

const endsOf =(connectionId: string): readonly string[] => {
  const [source, rest] = connectionId.split('---')
  return [source, (rest ?? '').split('@@')[0]]
}

export const membershipWithout = (membership: Membership, removed: ReadonlySet<string>): Membership => {
  const stable = new Set([...removed].map(stableEntityId))
  const gone = (id: string): boolean => stable.has(stableEntityId(id))
  const groupingWithout = (group: AuthoredGrouping): AuthoredGrouping => ({
    ...group,
    'entity-ids': group['entity-ids'].filter((id) => !gone(id)),
    ...(group.groups ? { groups: group.groups.map(groupingWithout) } : {}),
  })
  return {
    entity_ids: membership.entity_ids.filter((id) => !gone(id)),
    connection_ids: membership.connection_ids.filter((id) => !endsOf(id).some(gone)),
    ...(membership.authored_groupings
      ? { authored_groupings: membership.authored_groupings.map(groupingWithout) } : {}),
  }
}

/** What the picture a session starts from draws (a stored diagram, a candidate's start); null until read. */
export const membershipOf = (detail: PictureContext['diagram'] | null): DrawnMembership | null =>
  detail && {
    diagram_type: detail.diagram_type,
    name: detail.name,
    entity_ids: detail.entity_ids_used ?? [],
    connection_ids: detail.connection_ids_used ?? [],
    ...(detail.diagram_entities ? { diagram_entities: detail.diagram_entities } : {}),
    ...(detail.authored_groupings ? { authored_groupings: detail.authored_groupings } : {}),
  }
