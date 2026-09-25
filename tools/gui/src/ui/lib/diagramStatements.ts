/**
 * What a diagram states about the things it draws, kept in its own `diagram_entities` under one key per
 * kind of statement: `display_labels`, `display_icons`, `type_icons`. Each maps a key — an instance id,
 * or a type name — to the statement.
 *
 * The rules are the same for every kind, so they are stated once here: a statement map is read
 * leniently, and once the data has had a key it keeps it, even emptied, because the edit view merges
 * patches over the saved base and a patch that merely lacks the key cannot withdraw what the base
 * still states.
 */

const asMapping = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? { ...(value as Record<string, unknown>) } : {}

/** The statements under *key*, as a fresh mapping the caller may change. */
export const statementsIn = (diagramEntities: Record<string, unknown>, key: string): Record<string, unknown> =>
  asMapping(diagramEntities[key])

/** *diagramEntities* stating *statements* under *key*. */
export const withStatements = (
  diagramEntities: Record<string, unknown>, key: string, statements: Record<string, unknown>,
): Record<string, unknown> => {
  const { [key]: had, ...rest } = diagramEntities
  return Object.keys(statements).length || had !== undefined ? { ...rest, [key]: statements } : rest
}

/** The statements a diagram makes about one instance: they go when the instance does. */
export const INSTANCE_STATEMENT_KEYS = ['display_labels', 'display_icons'] as const

/**
 * Forget every statement about instances that are gone, so a removed instance leaves nothing behind
 * to resurface on a later copy. Returns the same object when there was nothing to forget.
 */
export const withoutInstanceStatements = (
  diagramEntities: Record<string, unknown>, instanceIds: readonly string[],
): Record<string, unknown> =>
  INSTANCE_STATEMENT_KEYS.reduce((data, key) => {
    const statements = statementsIn(data, key)
    if (!instanceIds.some((id) => id in statements)) return data
    for (const id of instanceIds) delete statements[id]
    return withStatements(data, key, statements)
  }, diagramEntities)
