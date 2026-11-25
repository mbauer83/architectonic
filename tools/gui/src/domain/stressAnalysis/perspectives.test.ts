import { describe, expect, it } from 'vitest'
import type { PerspectiveFramework } from '../schemas/stressEvaluation'
import { randomPerspective, unwritten } from './perspectives'

const frameworks: readonly PerspectiveFramework[] = [
  { id: 'pestle', name: 'PESTLE', perspectives: [
    { id: 'pestle.political', name: 'Political', kind: 'political', question: 'What if?' },
    { id: 'pestle.legal', name: 'Legal', kind: 'legal', question: 'What if?' },
  ] },
  { id: 'organisation', name: 'Organisation & people', perspectives: [
    { id: 'organisation.teams', name: 'Teams', kind: 'teams', question: 'What if?' },
  ] },
]

describe('the perspectives no stressor is written from', () => {
  it('are none while no stressor names a kind, because the kind is optional', () => {
    expect(unwritten(frameworks, ['', '  '])).toEqual(new Set())
  })

  it('are those whose kind no stressor carries, whatever its case and spacing', () => {
    expect(unwritten(frameworks, ['Political ', 'scale'])).toEqual(new Set(['pestle.legal', 'organisation.teams']))
  })
})

describe('a random perspective', () => {
  it('is drawn across every framework, and the pick decides which', () => {
    expect(randomPerspective(frameworks, 0)?.perspective.id).toBe('pestle.political')
    expect(randomPerspective(frameworks, 0.99))
      .toEqual({ framework: 'organisation', perspective: frameworks[1]?.perspectives[0] })
  })

  it('is none where nothing is offered', () => {
    expect(randomPerspective([], 0.5)).toBeNull()
  })
})
