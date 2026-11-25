/**
 * The entity edit form states an entity's attributes whole; the write path takes them as a patch.
 *
 * The server merges `properties` and `attribute_types` key by key: a key the body omits keeps its
 * stored value, and only a key mapped to `null` is removed. A form that edits the whole map must
 * therefore name every key it took away — leaving a deleted row out of the body is read as "leave
 * it as it is", and the attribute survives the save.
 *
 * **A row left empty states nothing.** An empty value cell is unstated wherever the model reads one, so
 * a row the form shows for a schema attribute nobody filled in is not a property: sent as `""` it would
 * write an empty row on every save, and a save that changed nothing would read as a change to the
 * attribute. Emptying a row that held a value removes the attribute.
 */

/** The stored keys of an entity's attribute maps, captured when an edit starts. */
export interface AttributeBaseline {
  /** The attributes the entity states: those with a value, never an empty one (`statedKeys`). */
  readonly propertyKeys: readonly string[]
  readonly attributeTypeKeys: readonly string[]
}

export const NO_ATTRIBUTES: AttributeBaseline = { propertyKeys: [], attributeTypeKeys: [] }

/** Whether a value, as the form holds it, states anything: an empty or blank one does not. */
export const isStated = (value: string): boolean => value.trim() !== ''

/** The keys of *properties* that state a value: what a patch may have to remove. */
export const statedKeys = (properties: Readonly<Record<string, string>>): string[] =>
  Object.entries(properties).filter(([, value]) => isStated(value)).map(([key]) => key)

/** `after`, plus a removal for every key of `before` that `after` no longer states. */
export const patchReplacing = <V>(
  before: readonly string[],
  after: Readonly<Record<string, V>>,
): Record<string, V | null> => ({
  ...Object.fromEntries(before.filter((key) => !Object.hasOwn(after, key)).map((key) => [key, null])),
  ...after,
})

/** One attribute row as the form holds it: a key, its lexical value, and its ad-hoc type. */
export interface AttributeRow {
  readonly key: string
  readonly value: string
  readonly adHocType: string
}

export interface AttributesPatch {
  readonly properties: Record<string, string | null>
  /** Absent when there is nothing to say: no ad-hoc type stated, and none to remove. */
  readonly attribute_types?: Record<string, string | null>
}

/**
 * The rows as a patch over what the entity had.
 *
 * A stored attribute type is the form's to remove only where the form states that attribute ad hoc,
 * or no longer states it at all. A type stored against a schema-declared attribute the form still
 * shows is left alone: the schema types that row, so the form never sends a type for it and has no
 * basis for withdrawing one.
 */
export const attributesPatch = (
  baseline: AttributeBaseline,
  rows: readonly AttributeRow[],
  isSchemaDeclared: (key: string) => boolean,
): AttributesPatch => {
  const stated = rows
    .map((row) => ({ ...row, key: row.key.trim() }))
    .filter((row) => row.key !== '' && isStated(row.value))
  const properties = Object.fromEntries(stated.map((row) => [row.key, row.value]))
  const adHocTypes = Object.fromEntries(
    stated
      .filter((row) => !isSchemaDeclared(row.key) && row.adHocType !== 'string')
      .map((row) => [row.key, row.adHocType]),
  )
  const schemaTyped = new Set(stated.map((row) => row.key).filter(isSchemaDeclared))
  const attributeTypes = patchReplacing(
    baseline.attributeTypeKeys.filter((key) => !schemaTyped.has(key)),
    adHocTypes,
  )
  return {
    properties: patchReplacing(baseline.propertyKeys, properties),
    ...(Object.keys(attributeTypes).length ? { attribute_types: attributeTypes } : {}),
  }
}
