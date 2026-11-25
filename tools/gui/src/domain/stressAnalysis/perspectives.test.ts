import { describe, expect, it } from 'vitest'
import type { PerspectiveFramework } from '../schemas/stressEvaluation'
import { randomPerspective } from './perspectives'

const frameworks: readonly PerspectiveFramework[] = [
  { id: 'pestle', name: 'PESTLE', perspectives: [
    { id: 'pestle.political', name: 'Political', kind: 'political', question: 'What if?' },
    { id: 'pestle.legal', name: 'Legal', kind: 'legal', question: 'What if?' },
  ] },
  { id: 'organisation', name: 'Organisation & people', perspectives: [
    { id: 'organisation.teams', name: 'Teams', kind: 'teams', question: 'What if?' },
  ] },
]

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
