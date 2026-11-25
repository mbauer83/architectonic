/**
 * The element a panel row carries to the canvas is written and read by one module: the pair is held
 * together, over what the drag permits — an element with or without a type — and over what it refuses.
 */
import { describe, expect, it } from 'vitest'
import { carriedEntity, carriesEntity, carryEntity } from '../entityDrag'

/** A drag's data, as the browser keeps it between dragstart and drop. */
const transfer = (): DataTransfer => {
  const data = new Map<string, string>()
  return {
    setData: (type: string, value: string) => { data.set(type, value) },
    getData: (type: string) => data.get(type) ?? '',
    get types() { return [...data.keys()] },
    effectAllowed: 'none',
  } as unknown as DataTransfer
}

describe('an element carried by a drag', () => {
  it.each([
    { artifact_id: 'APP@1.a.portal', name: 'Portal', artifact_type: 'application-component' },
    { artifact_id: 'APP@1.a', name: 'A name — with “quotes” and, commas' },
  ])('arrives as it was sent: %o', (entity) => {
    const drag = transfer()
    carryEntity(drag, entity)
    expect(carriesEntity(drag)).toBe(true)
    expect(carriedEntity(drag)).toEqual(entity)
  })

  it('is nothing when the drag carries something else, or something unreadable', () => {
    const other = transfer()
    other.setData('text/plain', 'APP@1.a')
    expect(carriesEntity(other)).toBe(false)
    expect(carriedEntity(other)).toBeNull()
    expect(carriedEntity(null)).toBeNull()
    const garbled = transfer()
    carryEntity(garbled, { artifact_id: 'APP@1.a', name: 'A' })
    garbled.setData(garbled.types[0], '{"artifact_id": 1}')
    expect(carriedEntity(garbled)).toBeNull()
    garbled.setData(garbled.types[0], 'not json')
    expect(carriedEntity(garbled)).toBeNull()
  })
})
