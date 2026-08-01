/**
 * Pure helper for the "save current filters as viewpoint" entry point: turns the
 * entities-list view's ad-hoc domain/type filters into an `entity_criteria` group in the
 * canonical wire mapping shape, ready to hand to the viewpoints management view's create
 * flow as a seed.
 */

import type { ColumnSpecNode, PresentationNode } from '../../domain/viewpointPresentation'
import type { EntityItemSummary, EntitySummary, ProjectedOccurrence, ViewpointProjection } from '../../domain'
import { getEntityConnectionTotal } from '../lib/domains'

/** Sort keys the server resolves over the whole filtered population, before paginating. */
export const SERVER_SORT_KEYS: readonly string[] = ['name', 'artifact_type', 'status', 'domain', 'last_updated']

/** Connection counts are computed for the rows of the current page only, so ordering by them
 * can only ever mean "within this page" — which is why the column says so in its header. */
export type ConnectionCountSortKey = 'in' | 'sym' | 'out' | 'total'

export const isServerSortKey = (key: string | null): boolean =>
  key !== null && SERVER_SORT_KEYS.includes(key)

/** Page-scoped ordering by a connection count; anything else is already in server order. */
export const sortEntityRows = (
  items: readonly EntitySummary[],
  sortKey: string | null,
  sortOrder: 1 | -1,
): EntitySummary[] => {
  if (!sortKey || isServerSortKey(sortKey)) return [...items]
  const compare = (left: number, right: number) =>
    left < right ? -1 * sortOrder : left > right ? 1 * sortOrder : 0
  return [...items].sort((a, b) => {
    if (sortKey === 'in') return compare(a.conn_in ?? 0, b.conn_in ?? 0)
    if (sortKey === 'sym') return compare(a.conn_sym ?? 0, b.conn_sym ?? 0)
    if (sortKey === 'out') return compare(a.conn_out ?? 0, b.conn_out ?? 0)
    return compare(getEntityConnectionTotal(a), getEntityConnectionTotal(b))
  })
}

export const filtersToEntityCriteriaMapping = (domain: string, artifactType: string): Record<string, unknown> => {
  const children: Record<string, unknown>[] = []
  if (domain) children.push({ kind: 'condition', attribute: 'domain', comparator: 'eq', value: domain })
  if (artifactType) children.push({ kind: 'condition', attribute: 'type', comparator: 'eq', value: artifactType })
  return { kind: 'group', conjunction: 'and', children }
}

// ── Viewpoint-driven table execution ─────────────────────────────────────────────

/** Same shape as `GraphExploreView.helpers.ts`'s function of the same name — kept as a
 * small local duplicate rather than a cross-view import (an established convention here). */
export const projectionByItemId = (projection: ViewpointProjection | null): ReadonlyMap<string, ProjectedOccurrence> =>
  new Map((projection?.items ?? []).map((item) => [item.item_id, item]))

const formatColumnValue = (value: unknown): string =>
  Array.isArray(value) ? value.map((item) => String(item)).join(', ') : String(value)

/** Column resolution order: the execution's server-resolved `column_values` first (they
 * carry every authored source — schema attributes and `derived.<name>` included — with
 * explicit nulls for missing values), then the reserved paths the fixed summary carries
 * directly. Null means "this entity has no value", rendered as an em dash. */
export const resolveSummaryColumnValue = (entity: EntityItemSummary, source: string): string | null => {
  const serverValues = entity.column_values
  if (serverValues != null && source in serverValues) {
    const value = serverValues[source]
    return value == null ? null : formatColumnValue(value)
  }
  switch (source) {
    case 'id': return entity.id
    case 'name': return entity.name
    case 'type': return entity.type
    case 'specialization': return entity.specialization_slugs.join(', ') || null
    case 'group': return entity.group
    case 'status': return entity.status || null
    case 'version': return entity.version || null
    default: return null
  }
}

export const RESOLVABLE_COLUMN_SOURCES: readonly string[] = [
  'id', 'name', 'type', 'specialization', 'group', 'status', 'version',
]

/** A column source is renderable when the server resolved it into `column_values` or
 * the fixed summary carries it directly — anything else gets the header's
 * "not available" marker instead of a silently blank column. */
export const isColumnSourceResolvable = (source: string, entity?: EntityItemSummary): boolean =>
  (entity?.column_values != null && source in entity.column_values) || RESOLVABLE_COLUMN_SOURCES.includes(source)

export interface TableColumn {
  readonly label: string
  readonly source: string
}

const DEFAULT_TABLE_COLUMNS: readonly TableColumn[] = [
  { label: 'Name', source: 'name' },
  { label: 'Type', source: 'type' },
  { label: 'Specialization', source: 'specialization' },
  { label: 'Group', source: 'group' },
]

/** A definition's authored `columns` for the table representation, else the same
 * default set the plain entity catalog shows. */
export const effectiveTableColumns = (columns: readonly ColumnSpecNode[] | null): readonly TableColumn[] =>
  columns && columns.length > 0
    ? columns.map((c) => ({ label: c.label || c.source, source: c.source }))
    : DEFAULT_TABLE_COLUMNS

/** `group_by` resolves against the fixed entity summary's three well-known non-attribute
 * dimensions, matching `GraphExploreView.helpers.ts::groupKeyFor` — an arbitrary
 * profile-attribute path falls back to `type` (recorded, not silently mis-grouped). */
export const groupKeyForEntity = (entity: EntityItemSummary, groupBy: string | null): string => {
  if (groupBy === 'group') return entity.group
  if (groupBy === 'specialization') return entity.specialization_slugs[0] ?? '(none)'
  return entity.type
}

export interface TableRowGroup {
  readonly groupKey: string
  readonly entities: readonly EntityItemSummary[]
}

/** Groups the retained population into ordered sections. `groupBy === null` returns one
 * ungrouped section (empty `groupKey`) so the table renders flat, as today. */
export const groupTableRows = (
  entities: readonly EntityItemSummary[],
  groupBy: string | null,
): readonly TableRowGroup[] => {
  if (groupBy === null) return entities.length > 0 ? [{ groupKey: '', entities }] : []
  const byKey = new Map<string, EntityItemSummary[]>()
  for (const entity of entities) {
    const key = groupKeyForEntity(entity, groupBy)
    const bucket = byKey.get(key)
    if (bucket) bucket.push(entity)
    else byKey.set(key, [entity])
  }
  return [...byKey.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([groupKey, groupEntities]) => ({ groupKey, entities: groupEntities }))
}

export type SortDirection = 'asc' | 'desc'

/** Stable sort by a column source's resolved display value (missing values last),
 * numeric-aware so versions/counts don't sort lexicographically. */
export const sortEntitiesBy = (
  entities: readonly EntityItemSummary[],
  source: string,
  direction: SortDirection,
): EntityItemSummary[] => {
  const factor = direction === 'asc' ? 1 : -1
  return [...entities].sort((a, b) => {
    const left = resolveSummaryColumnValue(a, source)
    const right = resolveSummaryColumnValue(b, source)
    if (left === null && right === null) return 0
    if (left === null) return 1
    if (right === null) return -1
    const leftNum = Number(left)
    const rightNum = Number(right)
    if (!Number.isNaN(leftNum) && !Number.isNaN(rightNum)) return (leftNum - rightNum) * factor
    return left.localeCompare(right) * factor
  })
}

/** The Style column earns its slot only when the definition actually styles table rows
 * (a `badges` rule or default) — a permanently empty column is noise, not a feature. */
export const hasBadgeStyling = (presentation: PresentationNode | null): boolean =>
  presentation !== null
  && (presentation.stylingRules.some((rule) => rule.capability === 'badges')
    || 'badges' in presentation.defaultStyle)

/** The list's own navigation targets — a row's detail page and the create surface — re-exported so
 * the view reads them from the module that already holds its other route decisions. */
export { entityCreateRoute, entityDetailRoute } from '../router/artifactRoutes'
