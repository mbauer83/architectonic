import type { DiagramOwnEntityTypeUiConfig, EntityDisplayInfo } from '../../../domain'

export interface C4RoleInfo {
  label: string
  entityType: string
}

export interface C4EntityGroup {
  label: string
  entityType: string
  entities: EntityDisplayInfo[]
}

/**
 * Builds a map from ArchiMate artifact_type → C4 role info,
 * derived from the diagram type's diagram_only_types config.
 */
export function buildC4RoleMap(
  diagramOnlyTypes: ReadonlyArray<DiagramOwnEntityTypeUiConfig>,
): Map<string, C4RoleInfo> {
  const map = new Map<string, C4RoleInfo>()
  for (const dot of diagramOnlyTypes) {
    const info: C4RoleInfo = { label: dot.label, entityType: dot.entity_type }
    if (!map.has(dot.entity_type)) map.set(dot.entity_type, info)
    for (const archType of dot.permitted_mappings.entity_types) {
      if (!map.has(archType)) map.set(archType, info)
    }
  }
  return map
}

/**
 * Group derived entities by C4 role (preserving diagram_only_types order).
 * The scope entity is excluded from groups — it is rendered separately.
 */
export function groupEntitiesByRole(
  entities: ReadonlyArray<EntityDisplayInfo>,
  scopeEntityId: string,
  diagramOnlyTypes: ReadonlyArray<DiagramOwnEntityTypeUiConfig>,
): C4EntityGroup[] {
  const roleMap = buildC4RoleMap(diagramOnlyTypes)
  const groupMap = new Map<string, C4EntityGroup>()
  for (const dot of diagramOnlyTypes) {
    groupMap.set(dot.entity_type, {
      label: dot.plural ?? dot.label + 's',
      entityType: dot.entity_type,
      entities: [],
    })
  }
  for (const entity of entities) {
    if (entity.artifact_id === scopeEntityId) continue
    const role = roleMap.get(entity.artifact_type)
    const key = role?.entityType ?? '__other__'
    if (!groupMap.has(key)) {
      groupMap.set(key, { label: 'Other', entityType: key, entities: [] })
    }
    groupMap.get(key)!.entities.push(entity)
  }
  return [...groupMap.values()].filter(g => g.entities.length > 0)
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
