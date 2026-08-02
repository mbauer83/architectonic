/**
 * Rows for the preview's derived-entity checklist.
 *
 * Two facts about a derived entity decide how its row behaves, and the checklist honoured
 * neither. `excluded` is the server's own verdict, so a server-side exclusion rendered as
 * unchecked-but-included. `role` says whether the entity is the diagram's scope root — the
 * engine will not exclude that one, so offering a checkbox for it offers nothing.
 *
 * `role` and `item_type` are the diagram-type module's vocabulary. Generic code must not
 * interpret them; the single comparison against the scope role is the whole exception, and it
 * lives here so no view re-derives it.
 */

import type { DerivedEntity } from '../../domain/schemas/diagrams'

/** The one role value generic code reads: the entity the diagram is *about*. */
const SCOPE_ROLE = 'scope'

const SCOPE_NOTE = 'The diagram is scoped to this entity — excluding it would leave nothing to draw.'

export interface DerivedEntityRow {
  readonly id: string
  readonly name: string
  readonly itemType: string
  /** Whether the entity will be drawn: neither the author nor the engine has excluded it. */
  readonly included: boolean
  /** Whether inclusion is the author's to change at all. */
  readonly fixed: boolean
  /** Why it is fixed, for the row's title — empty when it is not. */
  readonly note: string
}

export const derivedEntityRows = (
  derived: readonly DerivedEntity[],
  excludedIds: ReadonlySet<string>,
): readonly DerivedEntityRow[] =>
  derived.map((item) => {
    const fixed = item.role === SCOPE_ROLE
    return {
      id: item.id,
      name: item.name,
      itemType: item.item_type,
      included: fixed || !(item.excluded || excludedIds.has(item.id)),
      fixed,
      note: fixed ? SCOPE_NOTE : '',
    }
  })

/** How many rows the diagram will leave out — the count the header badge reports. */
export const excludedRowCount = (rows: readonly DerivedEntityRow[]): number =>
  rows.filter((row) => !row.included).length
