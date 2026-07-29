import { describe, it, expect } from 'vitest'
import {
  addItem,
  moveItem,
  parseArrayValue,
  removeItem,
  serializeArrayValue,
} from './arrayPropertyValue'

describe('parseArrayValue', () => {
  it('parses a JSON array of strings', () => {
    expect(parseArrayValue('["a","b"]')).toEqual(['a', 'b'])
  })

  it('stringifies non-string items so they stay editable', () => {
    expect(parseArrayValue('[1, true]')).toEqual(['1', 'true'])
  })

  it('is empty for blank, non-array, or malformed input (never throws)', () => {
    expect(parseArrayValue('')).toEqual([])
    expect(parseArrayValue('   ')).toEqual([])
    expect(parseArrayValue('"not an array"')).toEqual([])
    expect(parseArrayValue('[unclosed')).toEqual([])
  })
})

describe('serializeArrayValue', () => {
  it('round-trips string items', () => {
    expect(serializeArrayValue(['a', 'b'], { type: 'string' })).toBe('["a","b"]')
  })

  it('drops blank items', () => {
    expect(serializeArrayValue(['a', '  ', 'b'], { type: 'string' })).toBe('["a","b"]')
  })

  it('an empty list serializes to "" so an optional array stays absent', () => {
    expect(serializeArrayValue([], { type: 'string' })).toBe('')
    expect(serializeArrayValue(['', '  '], { type: 'string' })).toBe('')
  })

  it('types number and boolean items as JSON scalars', () => {
    expect(serializeArrayValue(['1', '2'], { type: 'integer' })).toBe('[1,2]')
    expect(serializeArrayValue(['true', 'false'], { type: 'boolean' })).toBe('[true,false]')
  })

  it('keeps an unparseable number as a string rather than emitting NaN', () => {
    expect(serializeArrayValue(['x'], { type: 'number' })).toBe('["x"]')
  })
})

describe('mutations', () => {
  it('adds an item', () => {
    expect(addItem(['a'], 'b')).toEqual(['a', 'b'])
    expect(addItem(['a'])).toEqual(['a', ''])
  })

  it('removes an item by index', () => {
    expect(removeItem(['a', 'b', 'c'], 1)).toEqual(['a', 'c'])
  })

  it('moves an item up and down', () => {
    expect(moveItem(['a', 'b', 'c'], 2, -1)).toEqual(['a', 'c', 'b'])
    expect(moveItem(['a', 'b', 'c'], 0, 1)).toEqual(['b', 'a', 'c'])
  })

  it('clamps a move at the ends (no-op)', () => {
    expect(moveItem(['a', 'b'], 0, -1)).toEqual(['a', 'b'])
    expect(moveItem(['a', 'b'], 1, 1)).toEqual(['a', 'b'])
  })
})
