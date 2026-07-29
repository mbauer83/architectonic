/**
 * Property-row reconciliation for schema-driven entity forms.
 *
 * When the effective attribute schema changes (entity type or specialization
 * selected), the form's property rows must follow the new schema without
 * discarding what the user already typed: schema-backed rows keep their
 * values, rows the user added by hand survive, and values entered under the
 * previous schema are kept as ad-hoc rows rather than silently dropped.
 */

export interface PropertyRow {
  key: string
  value: string
  adHocType: 'string' | 'integer' | 'number' | 'boolean' | 'array'
}

export interface SchemaRowSource {
  properties: readonly string[]
  descriptors: Readonly<Record<string, { default?: string } | undefined>>
}

export const rowsFromSchema = (info: SchemaRowSource): PropertyRow[] =>
  info.properties.map((key) => ({
    key,
    value: info.descriptors[key]?.default ?? '',
    adHocType: 'string',
  }))

/**
 * Reconcile existing rows against a newly loaded schema.
 *
 * - Every schema property gets a row, reusing the existing row's value (and
 *   ad-hoc type) when one exists, otherwise the schema default.
 * - Rows not covered by the new schema survive when the user added them by
 *   hand (key outside `previousSchemaKeys`) or already typed a value into
 *   them; empty rows that only existed because the previous schema listed
 *   them are dropped.
 */
export const reconcileRowsWithSchema = (
  existing: readonly PropertyRow[],
  previousSchemaKeys: readonly string[],
  info: SchemaRowSource,
): PropertyRow[] => {
  const byKey = new Map(existing.map((row) => [row.key, row]))
  const schemaKeys = new Set(info.properties)
  const schemaRows = info.properties.map((key) => {
    const row = byKey.get(key)
    return row
      ? { ...row }
      : { key, value: info.descriptors[key]?.default ?? '', adHocType: 'string' as const }
  })
  const previous = new Set(previousSchemaKeys)
  const carriedRows = existing
    .filter((row) => !schemaKeys.has(row.key))
    .filter((row) => !previous.has(row.key) || row.value.trim() !== '')
    .map((row) => ({ ...row }))
  return [...schemaRows, ...carriedRows]
}
