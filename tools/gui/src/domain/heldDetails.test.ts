import { describe, expect, it } from 'vitest'
import type { EntityDetail } from '.'
import { shownValue, withHeldDetails } from './heldDetails'

const detail = {
  artifact_id: 'SRV@1712870400.Uv9Wx9.repository-promotion-service', name: 'Repository Promotion Service',
  status: 'active', summary: 'Promotes', notes: '', group: 'core', keywords: ['promotion'], specializations: [],
  properties: { owner: 'Ops' },
} as unknown as EntityDetail

describe('an element\'s details as something other than the model holds them', () => {
  it('are what that holds, laid over the model\'s', () => {
    const held = withHeldDetails(detail, {
      name: 'Promotion Review Service', summary: 'Reviews', keywords: ['review'], properties: { owner: 'Platform' },
    })
    expect([held.name, held.summary, held.keywords, held.properties, held.status])
      .toEqual(['Promotion Review Service', 'Reviews', ['review'], { owner: 'Platform' }, 'active'])
  })

  it('are the model\'s where nothing is held', () => {
    expect(withHeldDetails(detail, {})).toEqual(detail)
  })
})

describe('a value shown as what lies beneath', () => {
  it('reads as a line of text, a dash for nothing', () => {
    expect([shownValue('x'), shownValue(''), shownValue(null), shownValue(['a', 'b']), shownValue([]), shownValue({ k: 1 })])
      .toEqual(['x', '—', '—', 'a, b', '—', '{"k":1}'])
  })
})
