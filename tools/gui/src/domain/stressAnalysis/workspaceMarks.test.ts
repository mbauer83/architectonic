import { describe, expect, it } from 'vitest'
import { diffMarks, framedMarks, hitMarks } from './workspaceMarks'

const SERVICE = 'SRV@1712870400.Uv9Wx9.repository-promotion-service'
const ARTIFACTS = 'PRC@1712870400.0Rz5Ex.promote-artifacts'

describe('the workspace marks', () => {
  it('marks what one stressor hits, keyed as the drawing keys an element', () => {
    const marks = hitMarks(new Map([['S1', [SERVICE, SERVICE]]]))
    expect([...marks]).toEqual([['SRV@1712870400.Uv9Wx9', { kind: 'hit', tag: 'hit', title: 'Hit by the stressor in focus' }]])
  })

  it('counts, with an end state in focus, how many of its stressors hit each component', () => {
    const marks = hitMarks(new Map([['S1', [SERVICE, ARTIFACTS]], ['S2', [ARTIFACTS]]]))
    expect(marks.get('PRC@1712870400.0Rz5Ex')?.tag).toBe('hit by 2 of 2')
    expect(marks.get('SRV@1712870400.Uv9Wx9')?.tag).toBe('hit by 1 of 2')
  })

  it('marks what a comparison added, changed and removed, and leaves a relation to the table', () => {
    const marks = diffMarks([
      { kind: 'entity', target: SERVICE, change: 'edited', fields: { name: { before: 'a', after: 'b' } } },
      { kind: 'entity', target: '$ref:queue', change: 'added', fields: {} },
      { kind: 'entity', target: ARTIFACTS, change: 'removed', fields: {} },
      {
        kind: 'connection', change: 'added', fields: {},
        target: { source_entity: SERVICE, connection_type: 'archimate-access', target_entity: ARTIFACTS },
      },
    ])
    expect([...marks].map(([id, mark]) => [id, mark.kind, mark.tag])).toEqual([
      ['SRV@1712870400.Uv9Wx9', 'edited', '~'], ['$ref:queue', 'added', '+'], ['PRC@1712870400.0Rz5Ex', 'removed', '−'],
    ])
    expect(marks.get('SRV@1712870400.Uv9Wx9')?.title).toBe('Changed: a field differs from the base (name)')
  })

  it('frames what a row or a choice is about', () => {
    expect([...framedMarks([SERVICE], 'why')]).toEqual([['SRV@1712870400.Uv9Wx9', { kind: 'framed', tag: '', title: 'why' }]])
  })
})
