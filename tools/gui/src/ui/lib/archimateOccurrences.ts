import type { EntityDisplayInfo, DiagramContextEntity } from '../../domain'

export interface ArchimateOccurrence {
  id: string
  backing_entity_id: string
  visual_role?: string
}

type OccurrenceEntity = Pick<EntityDisplayInfo | DiagramContextEntity, 'artifact_id' | 'display_alias' | 'name'>

export const isArchimateDiagramType = (diagramType: string | null | undefined): boolean =>
  !!diagramType && (diagramType === 'archimate' || diagramType.startsWith('archimate-'))

export const occurrenceItems = (diagramEntities: Record<string, unknown>): ArchimateOccurrence[] => {
  const raw = diagramEntities.occurrence
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is ArchimateOccurrence =>
    !!item
    && typeof item === 'object'
    && typeof (item as Record<string, unknown>).id === 'string'
    && typeof (item as Record<string, unknown>).backing_entity_id === 'string',
  )
}

/**
 * Identifies one *drawing* of an entity.
 *
 * Expansion state, and every other per-row concern, is per drawing rather than per entity: an
 * entity drawn twice has two rows, and opening one must not open the other.
 */
export const drawingKey = (entityId: string, occurrenceId: string | null): string =>
  `${entityId}::${occurrenceId ?? 'base'}`

/** Every extra drawing of *entityId*, in the order the diagram declares them. */
export const occurrencesOf = (
  diagramEntities: Record<string, unknown>,
  entityId: string,
): ArchimateOccurrence[] =>
  occurrenceItems(diagramEntities).filter((item) => item.backing_entity_id === entityId)

/** "2nd", "3rd", … — how a drawing is named to the reader. The base drawing is unnamed. */
export const occurrenceOrdinal = (index: number): string => {
  const position = index + 2
  const suffix = position % 10 === 1 && position % 100 !== 11 ? 'st'
    : position % 10 === 2 && position % 100 !== 12 ? 'nd'
      : position % 10 === 3 && position % 100 !== 13 ? 'rd' : 'th'
  return `${position}${suffix}`
}

export const occurrenceCount = (
  diagramEntities: Record<string, unknown>,
  entityId: string,
): number => occurrenceItems(diagramEntities).filter((item) => item.backing_entity_id === entityId).length

const safeLocalId = (value: string): string =>
  value.trim().replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'entity'

const nextOccurrenceId = (
  diagramEntities: Record<string, unknown>,
  entity: OccurrenceEntity,
): string => {
  const existing = new Set(occurrenceItems(diagramEntities).map((item) => item.id))
  const stem = `occ-${safeLocalId(entity.display_alias || entity.name || entity.artifact_id)}`
  let index = occurrenceCount(diagramEntities, entity.artifact_id) + 2
  let candidate = `${stem}-${index}`
  while (existing.has(candidate)) {
    index += 1
    candidate = `${stem}-${index}`
  }
  return candidate
}

/** Draw *entity* once more, handing back the new drawing's id along with the diagram. */
export const addOccurrenceFor = (
  diagramEntities: Record<string, unknown>,
  entity: OccurrenceEntity,
): { diagramEntities: Record<string, unknown>, occurrenceId: string } => {
  const occurrenceId = nextOccurrenceId(diagramEntities, entity)
  return {
    occurrenceId,
    diagramEntities: {
      ...diagramEntities,
      occurrence: [
        ...occurrenceItems(diagramEntities),
        { id: occurrenceId, backing_entity_id: entity.artifact_id },
      ],
    },
  }
}

export const addOccurrence = (
  diagramEntities: Record<string, unknown>,
  entity: OccurrenceEntity,
): Record<string, unknown> => addOccurrenceFor(diagramEntities, entity).diagramEntities

export const removeOccurrence = (
  diagramEntities: Record<string, unknown>,
  occurrenceId: string,
): Record<string, unknown> => ({
  ...diagramEntities,
  occurrence: occurrenceItems(diagramEntities).filter((item) => item.id !== occurrenceId),
})
