/**
 * The element types offered at a point (sketch 03·2): recently used first, then those on the diagram,
 * then each layer under its framework; a filter narrows by the type's words; the recent list lives in
 * this browser and survives storage that refuses or holds nonsense.
 */
import { describe, expect, it } from 'vitest'
import {
  RECENT_TYPES_KEY, RECENT_TYPES_SHOWN, noteRecentType, recentTypes, typeSections, typeWords,
} from '../canvasTypeList'

const PALETTE = [
  { type: 'business-actor', domain: 'business' },
  { type: 'business-object', domain: 'business' },
  { type: 'process', domain: 'common' },
  { type: 'service', domain: 'common' },
  { type: 'application-component', domain: 'application' },
]

const memory = (initial: Record<string, string> = {}) => {
  const held = new Map(Object.entries(initial))
  return { getItem: (key: string) => held.get(key) ?? null, setItem: (key: string, value: string) => void held.set(key, value) }
}

describe('the sections of the type list', () => {
  it('puts recent types first, then those on the diagram, then each layer in catalogue order', () => {
    const sections = typeSections(PALETTE, ['process', 'business-object'], ['service'])
    expect(sections.map((one) => one.key)).toEqual(['recent', 'here', 'domain:business', 'domain:application'])
    expect(sections[0]?.items.map((one) => one.type)).toEqual(['service'])
    expect(sections[0]?.note).toBe('in this browser')
    expect(sections[1]?.items.map((one) => one.type)).toEqual(['business-object', 'process'])
    expect(sections[2]?.items.map((one) => one.type)).toEqual(['business-actor'])
  })

  it('names the framework once, above its first layer', () => {
    const layers = typeSections(PALETTE, [], []).filter((one) => one.domain)
    expect(layers.map((one) => one.framework)).toEqual(['ArchiMate 4', undefined, undefined])
    expect(layers.map((one) => one.domain)).toEqual(['business', 'common', 'application'])
  })

  it('keeps a recent type only where the diagram type accepts it, and never twice', () => {
    const sections = typeSections(PALETTE, ['service'], ['service', 'goal'])
    expect(sections[0]?.items.map((one) => one.type)).toEqual(['service'])
    expect(sections.find((one) => one.key === 'here')).toBeUndefined()
  })

  it('narrows by the words of a type, dropping emptied sections and the framework heading', () => {
    const sections = typeSections(PALETTE, ['process'], [], 'Object')
    expect(sections.map((one) => one.key)).toEqual(['domain:business'])
    expect(sections[0]?.items.map((one) => one.type)).toEqual(['business-object'])
    expect(sections[0]?.framework).toBeUndefined()
    expect(typeSections(PALETTE, [], [], 'zzz')).toEqual([])
  })

  it('reads a type in words, kebab or camel', () => {
    expect(typeWords('business-object')).toBe('business object')
    expect(typeWords('applicationComponent')).toBe('application component')
  })
})

describe('the types used recently in this browser', () => {
  it('holds the newest first, once each, and only a few', () => {
    const store = memory()
    for (const type of ['a', 'b', 'c', 'd', 'e', 'f', 'b']) noteRecentType(type, store)
    expect(recentTypes(store)).toEqual(['b', 'f', 'e', 'd', 'c'])
    expect(recentTypes(store)).toHaveLength(RECENT_TYPES_SHOWN)
  })

  it('reads nothing from storage that is missing, refuses, or holds nonsense', () => {
    expect(recentTypes(null)).toEqual([])
    expect(recentTypes(memory({ [RECENT_TYPES_KEY]: '{not json' }))).toEqual([])
    expect(recentTypes(memory({ [RECENT_TYPES_KEY]: '{"a":1}' }))).toEqual([])
    expect(recentTypes(memory({ [RECENT_TYPES_KEY]: '["a", 3, "b"]' }))).toEqual(['a', 'b'])
    const refusing = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
    expect(recentTypes(refusing)).toEqual([])
    expect(() => noteRecentType('a', refusing)).not.toThrow()
  })
})
