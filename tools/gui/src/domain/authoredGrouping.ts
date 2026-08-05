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
export interface AuthoredGrouping {
  readonly label: string
  /** Entity ids, or occurrence ids for a specific drawing of one. */
  readonly 'entity-ids': readonly string[]
  readonly groups?: readonly AuthoredGrouping[]
  /** Honoured by the backend, never sent by this app: the look is derived from the members. */
  readonly stereotype?: string
}

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

/** Drop groups that would draw nothing, at any depth — an empty box is noise, not a statement. */
export const withoutEmptyGroups = (
  groups: readonly AuthoredGrouping[],
): readonly AuthoredGrouping[] =>
  groups
    .map((group) => ({ ...group, groups: withoutEmptyGroups(group.groups ?? []) }))
    .filter((group) => group['entity-ids'].length > 0 || (group.groups?.length ?? 0) > 0)
    .map((group) => (group.groups.length > 0 ? group : { label: group.label, 'entity-ids': group['entity-ids'] }))
