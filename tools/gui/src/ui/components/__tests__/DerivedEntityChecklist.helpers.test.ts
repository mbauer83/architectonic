import { describe, it, expect } from 'vitest'
import { derivedEntityRows, excludedRowCount } from '../DerivedEntityChecklist.helpers'
import type { DerivedEntity } from '../../../domain/schemas/diagrams'

const entity = (overrides: Partial<DerivedEntity> = {}): DerivedEntity => ({
  id: 'APP@1.aaa.thing', name: 'Thing', item_type: 'container', role: 'internal', excluded: false,
  ...overrides,
})

describe('derivedEntityRows', () => {
  it('marks the scope root fixed, because the engine will not exclude it', () => {
    // The checklist offered an unconditional checkbox for every row. Unchecking the scope root
    // did nothing at all — the diagram is scoped to it — so the control promised something it
    // could not deliver.
    const [row] = derivedEntityRows([entity({ role: 'scope' })], new Set())

    expect(row.fixed).toBe(true)
    expect(row.included).toBe(true)
    expect(row.note).not.toBe('')
  })

  it('leaves an ordinary row unchecked once the author has excluded it', () => {
    const [row] = derivedEntityRows([entity()], new Set(['APP@1.aaa.thing']))

    expect(row.fixed).toBe(false)
    expect(row.included).toBe(false)
    expect(row.note).toBe('')
  })

  it("honours the server's own exclusion, not only the author's", () => {
    // `excluded` was stripped on decode, so a server-side exclusion rendered as
    // unchecked-but-included: the checklist disagreed with the diagram it was previewing.
    const [row] = derivedEntityRows([entity({ excluded: true })], new Set())

    expect(row.included).toBe(false)
  })

  it('keeps the scope root included even if it arrives marked excluded', () => {
    const [row] = derivedEntityRows([entity({ role: 'scope', excluded: true })], new Set())

    expect(row.included).toBe(true)
  })

  it('forwards the diagram type’s own vocabulary without interpreting it', () => {
    const [row] = derivedEntityRows([entity({ item_type: 'person', role: 'external' })], new Set())

    expect(row.itemType).toBe('person')
    expect(row.fixed).toBe(false)
  })
})

describe('excludedRowCount', () => {
  it('counts every row the diagram will leave out, from either source', () => {
    const rows = derivedEntityRows(
      [
        entity({ id: 'a' }),
        entity({ id: 'b', excluded: true }),
        entity({ id: 'c' }),
        entity({ id: 'd', role: 'scope' }),
      ],
      new Set(['c']),
    )

    expect(excludedRowCount(rows)).toBe(2)
  })
})
