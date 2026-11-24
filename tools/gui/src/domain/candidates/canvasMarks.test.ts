import { describe, expect, it } from 'vitest'
import { diffMarks, framedMarks } from './canvasMarks'

const SERVICE = 'SRV@1712870400.Uv9Wx9.repository-promotion-service'
const ARTIFACTS = 'PRC@1712870400.0Rz5Ex.promote-artifacts'

describe('the canvas marks', () => {
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
