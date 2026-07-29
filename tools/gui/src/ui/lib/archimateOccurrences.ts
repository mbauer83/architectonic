import type { EntityDisplayInfo, EntitySummary } from '../../domain'

export interface ArchimateOccurrence {
  id: string
  backing_entity_id: string
  visual_role?: string
}

type OccurrenceEntity = Pick<EntityDisplayInfo | EntitySummary, 'artifact_id' | 'display_alias' | 'name'>

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

export const addOccurrence = (
  diagramEntities: Record<string, unknown>,
  entity: OccurrenceEntity,
): Record<string, unknown> => ({
  ...diagramEntities,
  occurrence: [
    ...occurrenceItems(diagramEntities),
    {
      id: nextOccurrenceId(diagramEntities, entity),
      backing_entity_id: entity.artifact_id,
    },
  ],
})

export const removeOccurrence = (
  diagramEntities: Record<string, unknown>,
  occurrenceId: string,
): Record<string, unknown> => ({
  ...diagramEntities,
  occurrence: occurrenceItems(diagramEntities).filter((item) => item.id !== occurrenceId),
})
