import type { GroupEntry, GroupList } from '../../domain/schemas/groups'

/**
 * The collection axes, and which entries a reader may file something into.
 *
 * Four axes exist and they are independent registries: a slug on one says nothing about the others,
 * so anything choosing a collection has to say which axis it is choosing from. The mapping from
 * axis to the key a `listGroups` answer carries it under lives here — singular in the ask, plural
 * on the wire — rather than at each caller that would otherwise pluralise it by hand.
 */
export type CollectionAxis = 'model-project' | 'diagram-collection' | 'document-collection'

const RESPONSE_KEY: Readonly<Record<CollectionAxis, keyof GroupList>> = {
  'model-project': 'model-projects',
  'diagram-collection': 'diagram-collections',
  'document-collection': 'document-collections',
}

/**
 * The collections something may be filed into, in the order the sidebar shows them.
 *
 * Archived ones are left out: an archive is where work goes when it stops being current, so
 * offering it as a destination invites filing new work into it. The server orders by
 * `(order, slug)` already, and re-sorting here would be a second opinion about a curated sequence.
 */
export const filableCollections = (
  list: GroupList | null, axis: CollectionAxis,
): readonly GroupEntry[] => (list?.[RESPONSE_KEY[axis]] ?? []).filter((entry) => !entry.archived)
