import type { EntityDisplayInfo } from '../../domain'

/**
 * What an instance is called on this diagram, as the diagram itself states it.
 *
 * `diagram-entities.display_labels` maps a instance id — the entity's artifact id for its base
 * instance, the occurrence id for a further one — to the label its box carries here. The element
 * keeps its name everywhere else; this is the diagram's say, not a rename, which is why it lives in
 * the diagram's own data and is written with it.
 */
export const DISPLAY_LABELS_KEY = 'display_labels'

export const displayLabelOverrides = (diagramEntities: Record<string, unknown>): Record<string, string> => {
  const raw = diagramEntities[DISPLAY_LABELS_KEY]
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>)
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].trim() !== ''),
  )
}

/** The label this diagram states for one instance, or undefined where it states none. */
export const displayLabelOf = (diagramEntities: Record<string, unknown>, instanceId: string): string | undefined =>
  displayLabelOverrides(diagramEntities)[instanceId]

/**
 * The key stays once the data has had it, even emptied. The edit view merges patches over the saved
 * base, and a patch that merely lacks the key cannot withdraw what the base still states.
 */
const withOverrides = (
  diagramEntities: Record<string, unknown>, overrides: Record<string, string>,
): Record<string, unknown> => {
  const { [DISPLAY_LABELS_KEY]: had, ...rest } = diagramEntities
  return Object.keys(overrides).length || had !== undefined ? { ...rest, [DISPLAY_LABELS_KEY]: overrides } : rest
}

/**
 * State a label for one instance, or withdraw the statement with `null` so the element speaks for
 * itself again. A label that is only whitespace is a withdrawal too: an empty box is never what
 * was meant.
 */
export const withDisplayLabel = (
  diagramEntities: Record<string, unknown>, instanceId: string, label: string | null,
): Record<string, unknown> => {
  const overrides = displayLabelOverrides(diagramEntities)
  const trimmed = label?.trim() ?? ''
  if (trimmed) overrides[instanceId] = trimmed
  else delete overrides[instanceId]
  return withOverrides(diagramEntities, overrides)
}

/** Forget the statements about instances that are gone, so a removed instance leaves nothing behind. */
export const withoutDisplayLabels = (
  diagramEntities: Record<string, unknown>, instanceIds: readonly string[],
): Record<string, unknown> => {
  const overrides = displayLabelOverrides(diagramEntities)
  if (!instanceIds.some((id) => id in overrides)) return diagramEntities
  for (const id of instanceIds) delete overrides[id]
  return withOverrides(diagramEntities, overrides)
}

/**
 * The label an instance's box carries right now: the diagram's statement, else what the body already
 * declares, else what the element calls itself.
 *
 * The middle case is a hand-laid body that calls an element something its record does not; without
 * it the editor would show a name the picture does not, and the first save would make the picture
 * agree with the editor rather than the other way round.
 */
export const drawnLabelFor = (
  diagramEntities: Record<string, unknown>,
  drawnLabels: Record<string, string>,
  instanceId: string,
  entity: Pick<EntityDisplayInfo, 'element_label' | 'name'>,
): string =>
  displayLabelOf(diagramEntities, instanceId) ?? drawnLabels[instanceId] ?? (entity.element_label || entity.name)

/**
 * Carry a hand-laid body's labels into the diagram's statement before a save regenerates the body.
 *
 * Only where the body disagrees with the element and the diagram states nothing yet: an instance the
 * body calls by the element's own name needs no statement, and one the diagram already labels has
 * had its say. Returns the patch to merge, or an empty one when there is nothing to carry.
 */
export const seededDisplayLabels = (
  diagramEntities: Record<string, unknown>,
  drawnLabels: Record<string, string>,
  entitiesById: ReadonlyMap<string, Pick<EntityDisplayInfo, 'element_label' | 'name'>>,
  backingEntityOf: (instanceId: string) => string,
): Record<string, unknown> => {
  const overrides = displayLabelOverrides(diagramEntities)
  const carried = { ...overrides }
  for (const [instanceId, drawn] of Object.entries(drawnLabels)) {
    if (instanceId in overrides) continue
    const entity = entitiesById.get(backingEntityOf(instanceId))
    if (!entity) continue
    if (drawn !== (entity.element_label || entity.name)) carried[instanceId] = drawn
  }
  return Object.keys(carried).length === Object.keys(overrides).length ? {} : { [DISPLAY_LABELS_KEY]: carried }
}
