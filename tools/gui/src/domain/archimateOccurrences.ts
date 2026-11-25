/**
 * An ArchiMate diagram's further drawings of its elements, as its `diagram-entities` states them: one
 * `occurrence` item per further drawing, its own id beside the entity it draws again. The one reading of
 * that statement in this app; `ui/lib/archimateOccurrences` writes it and re-exports this.
 */

export interface ArchimateOccurrence {
  id: string
  backing_entity_id: string
  visual_role?: string
}

export const occurrenceItems = (diagramEntities: Readonly<Record<string, unknown>>): ArchimateOccurrence[] => {
  const raw = diagramEntities.occurrence
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is ArchimateOccurrence =>
    !!item
    && typeof item === 'object'
    && typeof (item as Record<string, unknown>).id === 'string'
    && typeof (item as Record<string, unknown>).backing_entity_id === 'string',
  )
}
