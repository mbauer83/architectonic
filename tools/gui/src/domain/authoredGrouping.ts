/**
 * A labelled box a diagram draws that the model does not hold.
 *
 * The label is the point: "Write Requests" says something no element type does, so a grouping is
 * content rather than layout. Two things it deliberately does NOT carry:
 *
 * - **a look.** The backend derives it from the members — all in one domain gives that domain's
 *   look, several give the dashed ArchiMate grouping look — so the editor never asks for one. The
 *   wire type keeps `stereotype` optional because the backend still honours a deliberate override,
 *   but nothing in this app sends it.
 * - **a flat shape.** `groups` nests to any depth, and a member may name an occurrence id rather
 *   than an entity id, so an entity drawn twice can sit in a different box each time.
 */
import type { AuthoredGroupingWire } from './schemas/diagrams'

export type AuthoredGrouping = AuthoredGroupingWire

/** Every id claimed by *groups*, at any depth — what the editor greys out as already placed. */
export const claimedMemberIds = (groups: readonly AuthoredGrouping[]): ReadonlySet<string> => {
  const claimed = new Set<string>()
  const walk = (group: AuthoredGrouping): void => {
    for (const id of group['entity-ids']) claimed.add(id)
    for (const nested of group.groups ?? []) walk(nested)
  }
  for (const group of groups) walk(group)
  return claimed
}

/**
 * Drawing id → the label of the box holding it, innermost box winning.
 *
 * A drawing sits in at most one box, and the Included Entities list has to say which: without it
 * you cannot tell the drawing that is inside a box from one that is loose beside it, which is
 * exactly the state that reads as "nothing happened" when you place an entity in a group.
 */
export const groupLabelByMember = (
  groups: readonly AuthoredGrouping[],
): ReadonlyMap<string, string> => {
  const labels = new Map<string, string>()
  const walk = (group: AuthoredGrouping): void => {
    for (const id of group['entity-ids']) labels.set(id, group.label)
    for (const nested of group.groups ?? []) walk(nested)
  }
  for (const group of groups) walk(group)
  return labels
}

/** The drawings one box holds directly, in the order it holds them. */
export const membersOfGroup = (group: AuthoredGrouping | undefined): readonly string[] =>
  group?.['entity-ids'] ?? []

/**
 * Put *memberId* in the box that holds *hostId*, at whatever depth that box sits.
 *
 * What "add this from inside the box" means: a neighbour pulled in from a drawing that lives in a
 * box joins that box, or it lands loose outside the very grouping it was reached through. Returns
 * the groups unchanged when the host is in no box — reaching a neighbour from a loose drawing
 * places nothing.
 */
export const withMemberBeside = (
  groups: readonly AuthoredGrouping[], hostId: string, memberId: string,
): readonly AuthoredGrouping[] =>
  groups.map((group) => {
    const members = group['entity-ids']
    if (members.includes(hostId)) {
      return members.includes(memberId) ? group : { ...group, 'entity-ids': [...members, memberId] }
    }
    const nested = group.groups ? withMemberBeside(group.groups, hostId, memberId) : undefined
    return nested === group.groups || nested === undefined ? group : { ...group, groups: [...nested] }
  })

/** Drop groups that would draw nothing, at any depth — an empty box is noise, not a statement. */
export const withoutEmptyGroups = (
  groups: readonly AuthoredGrouping[],
): readonly AuthoredGrouping[] =>
  groups
    .map((group) => ({ ...group, groups: withoutEmptyGroups(group.groups ?? []) }))
    .filter((group) => group['entity-ids'].length > 0 || (group.groups?.length ?? 0) > 0)
    .map((group) => (group.groups.length > 0 ? group : { label: group.label, 'entity-ids': group['entity-ids'] }))
