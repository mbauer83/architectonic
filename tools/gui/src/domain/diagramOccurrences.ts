/**
 * A diagram's further drawings of its elements, as its `diagram-entities` states them: one `occurrence`
 * item per further drawing, its own id beside the entity it draws again. Only a diagram whose type draws
 * occurrences holds them (`draws_occurrences` in the type catalogue; ArchiMate's views do). The one reading
 * of that statement in this app; `ui/lib/diagramOccurrences` writes it and re-exports this.
 */

export interface DiagramOccurrence {
  id: string
  backing_entity_id: string
  visual_role?: string
}

export const occurrenceItems = (diagramEntities: Readonly<Record<string, unknown>>): DiagramOccurrence[] => {
  const raw = diagramEntities.occurrence
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is DiagramOccurrence =>
    !!item
    && typeof item === 'object'
    && typeof (item as Record<string, unknown>).id === 'string'
    && typeof (item as Record<string, unknown>).backing_entity_id === 'string',
  )
}
