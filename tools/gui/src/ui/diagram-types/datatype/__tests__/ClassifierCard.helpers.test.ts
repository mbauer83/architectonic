import { describe, expect, it } from 'vitest'
import {
  appendMember,
  attrLabel,
  buildTypeOptions,
  moveInList,
  optionKey,
  refFromOptionKey,
  removeAt,
} from '../ClassifierCard.helpers'

const local = [
  { id: 'CLF@1.local.order', classifier_kind: 'class' as const, label: 'Order' },
]
const catalog = [
  {
    type_id: 'CLF@1.eng.customer',
    label: 'Customer',
    scope: 'engagement',
    host_diagram_id: 'DT-2',
  },
  {
    type_id: 'CLF@1.ent.money',
    label: 'Money',
    scope: 'enterprise',
    host_diagram_id: 'DT-3',
  },
]

describe('buildTypeOptions', () => {
  it('builds closed tagged-reference options in display groups', () => {
    const options = buildTypeOptions(['String'], local, catalog, 'DT-1')
    expect(options.map((option) => [option.group, option.label])).toEqual([
      ['Primitives', 'String'],
      ['This diagram', 'Order'],
      ['Engagement', 'Customer'],
      ['Enterprise', 'Money'],
    ])
  })

  it('deduplicates a local classifier already returned by discovery', () => {
    const options = buildTypeOptions(['String'], local, [
      ...catalog,
      {
        type_id: local[0].id,
        label: 'Order',
        scope: 'engagement',
        host_diagram_id: 'DT-1',
      },
    ], 'DT-1')
    expect(options.filter((option) => option.key === `classifier:${local[0].id}`)).toHaveLength(1)
  })

  it('keeps a classifier that shadows a primitive as a distinct choice', () => {
    const options = buildTypeOptions(['String'], [{
      id: 'CLF@1.local.string',
      classifier_kind: 'primitive',
      label: 'String',
    }], [], 'DT-1')
    expect(options.map((option) => option.key)).toEqual([
      'primitive:String',
      'classifier:CLF@1.local.string',
    ])
  })

  it('round-trips only known option keys', () => {
    const options = buildTypeOptions(['String'], local, [], 'DT-1')
    const classifierRef = { kind: 'classifier' as const, id: local[0].id }
    expect(refFromOptionKey(optionKey(classifierRef), options)).toEqual(classifierRef)
    expect(refFromOptionKey('free text', options)).toBeUndefined()
  })
})

describe('ordered key helpers', () => {
  const attrs = [
    { id: 'a1', name: 'tenant' },
    { id: 'a2', name: 'number' },
  ]

  it('resolves an attribute id to its current name (rename-free references)', () => {
    expect(attrLabel('a1', attrs)).toBe('tenant')
    expect(attrLabel('missing', attrs)).toBe('missing')
  })

  it('appends a member without repetition', () => {
    expect(appendMember(['a1'], 'a2')).toEqual(['a1', 'a2'])
    expect(appendMember(['a1'], 'a1')).toEqual(['a1'])
  })

  it('removes a member by index', () => {
    expect(removeAt(['a1', 'a2', 'a3'], 1)).toEqual(['a1', 'a3'])
  })

  it('reorders members, clamping at the ends', () => {
    expect(moveInList(['a1', 'a2', 'a3'], 0, 1)).toEqual(['a2', 'a1', 'a3'])
    expect(moveInList(['a1', 'a2'], 0, -1)).toEqual(['a1', 'a2'])
    expect(moveInList(['a1', 'a2'], 1, 1)).toEqual(['a1', 'a2'])
  })
})
