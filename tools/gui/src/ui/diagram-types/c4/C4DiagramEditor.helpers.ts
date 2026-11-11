import type { DerivedEntity, DiagramOwnEntityTypeUiConfig, EntityDisplayInfo } from '../../../domain'

export interface C4EntityGroup {
  label: string
  entityType: string
  entities: EntityDisplayInfo[]
}

/** The group an entity stands in before the server has classified it, as on a diagram not yet previewed. */
export const UNCLASSIFIED = '__unclassified__'

/**
 * Group derived entities under the C4 type the server's projection draws each as, in the order the
 * diagram type declares its own types. The scope entity is rendered separately and left out.
 *
 * The projection classifies by structure — the children of the scope container are its components, a
 * store is a database — so the answer is the server's. Reading it off the type table instead put every
 * application component under the first C4 type permitting one, and a component diagram listed its
 * components as software systems while the picture drew them as components.
 */
export function groupEntitiesByDrawnType(
  entities: ReadonlyArray<EntityDisplayInfo>,
  scopeEntityId: string,
  diagramOnlyTypes: ReadonlyArray<DiagramOwnEntityTypeUiConfig>,
  derived: ReadonlyArray<DerivedEntity> | null | undefined,
): C4EntityGroup[] {
  const drawnAs = new Map((derived ?? []).map(row => [row.id, row.item_type]))
  const groups = new Map<string, C4EntityGroup>(diagramOnlyTypes.map(dot => [
    dot.entity_type, { label: dot.plural ?? dot.label + 's', entityType: dot.entity_type, entities: [] },
  ]))
  for (const entity of entities) {
    if (entity.artifact_id === scopeEntityId) continue
    const drawn = drawnAs.get(entity.artifact_id)
    const key = derived == null ? UNCLASSIFIED : drawn !== undefined && groups.has(drawn) ? drawn : '__other__'
    if (!groups.has(key)) {
      groups.set(key, { label: key === UNCLASSIFIED ? 'Entities' : 'Other', entityType: key, entities: [] })
    }
    groups.get(key)!.entities.push(entity)
  }
  return [...groups.values()].filter(g => g.entities.length > 0)
}

/**
 * Parse _excluded_entity_ids from the raw diagramEntities record.
 * Returns an empty set for missing/malformed values.
 */
export function parseExcludedIds(diagramEntities: Record<string, unknown>): Set<string> {
  const raw = diagramEntities._excluded_entity_ids
  if (!Array.isArray(raw)) return new Set()
  return new Set(raw.filter((x): x is string => typeof x === 'string'))
}

/**
 * Derive the scope entity id from the raw diagramEntities payload that
 * EditDiagramView receives from the backend.
 *
 * Model-backed C4 diagrams: the backend injects _scope_entity_id from the
 * scoped-by binding into diagram_entities.  Standalone diagrams fall back to
 * the inline item with scope=true that the frontend writes on scope selection.
 */
export function resolveScopeEntityId(diagramEntities: Record<string, unknown>): string {
  const explicit = diagramEntities._scope_entity_id
  if (typeof explicit === 'string' && explicit) return explicit
  for (const [key, items] of Object.entries(diagramEntities)) {
    if (key.startsWith('_') || !Array.isArray(items)) continue
    for (const item of items) {
      if (item && typeof item === 'object') {
        const r = item as Record<string, unknown>
        if (r.scope && r.entity_id && typeof r.entity_id === 'string') return r.entity_id
      }
    }
  }
  return ''
}
