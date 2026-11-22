/**
 * A diagram's membership without some of its entities: what a diagram write states once elements are
 * removed from the diagram (never from the model). The entities go from `entity_ids`, from every
 * grouping that lists them, and every connection with either end among them goes from
 * `connection_ids` — a connection id is `<source>---<target>@@<type>`.
 */
import type { AuthoredGrouping } from '../authoredGrouping'

export interface Membership {
  readonly entity_ids: readonly string[]
  readonly connection_ids: readonly string[]
  readonly authored_groupings?: readonly AuthoredGrouping[]
}

const endsOf = (connectionId: string): readonly string[] => {
  const [source, rest] = connectionId.split('---')
  return [source, (rest ?? '').split('@@')[0]]
}

const groupingWithout = (group: AuthoredGrouping, removed: ReadonlySet<string>): AuthoredGrouping => ({
  ...group,
  'entity-ids': group['entity-ids'].filter((id) => !removed.has(id)),
  ...(group.groups ? { groups: group.groups.map((nested) => groupingWithout(nested, removed)) } : {}),
})

export const membershipWithout = (membership: Membership, removed: ReadonlySet<string>): Membership => ({
  entity_ids: membership.entity_ids.filter((id) => !removed.has(id)),
  connection_ids: membership.connection_ids.filter((id) => !endsOf(id).some((end) => removed.has(end))),
  ...(membership.authored_groupings
    ? { authored_groupings: membership.authored_groupings.map((group) => groupingWithout(group, removed)) }
    : {}),
})
