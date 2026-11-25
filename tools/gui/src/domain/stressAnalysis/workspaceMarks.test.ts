import { describe, expect, it } from 'vitest'
import { hitMarks, stressorsTicking } from './workspaceMarks'

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
})

describe('an element selected on the canvas', () => {
  const ticks = [
    { stressor: 'S1', component: SERVICE }, { stressor: 'S2', component: ARTIFACTS }, { stressor: 'S3', component: SERVICE },
  ]
  it('marks the stressors that tick it, by the key the drawing gives it', () => {
    expect([...stressorsTicking(ticks, 'SRV@1712870400.Uv9Wx9')]).toEqual(['S1', 'S3'])
  })

  it('marks none when nothing is selected, or nothing ticks it', () => {
    expect(stressorsTicking(ticks, null).size).toBe(0)
    expect(stressorsTicking(ticks, 'ACT@1712870400.Nn7Oo7').size).toBe(0)
  })
})
