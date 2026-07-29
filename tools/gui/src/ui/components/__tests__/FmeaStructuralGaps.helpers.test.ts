import { describe, expect, it } from 'vitest'
import {
  GAPS_EXPLANATION,
  gapHeading,
  gapSummary,
  structuralGaps,
  typeAbbreviation,
} from '../FmeaStructuralGaps.helpers'
import type { VerificationIssue } from '../FmeaStructuralGaps.helpers'

function issue(overrides: Partial<VerificationIssue> = {}): VerificationIssue {
  return {
    severity: 'warning',
    code: 'W511',
    message: 'APP@one is load-bearing but appears in no control structure.',
    node_id: 'APP@one',
    witness: ['APP@a --archimate-serving--> APP@one'],
    ...overrides,
  }
}

describe('structuralGaps', () => {
  it('keeps only the load-bearing-unanalysed findings', () => {
    const gaps = structuralGaps([issue(), issue({ code: 'W512', node_id: 'APP@two' })])

    expect(gaps.map((gap) => gap.elementId)).toEqual(['APP@one'])
  })

  it('orders by how much relies on the element, so the list is not a hundred equals', () => {
    const gaps = structuralGaps([
      issue({ node_id: 'APP@light', witness: ['w1'] }),
      issue({ node_id: 'APP@heavy', witness: ['w1', 'w2', 'w3'] }),
    ])

    expect(gaps.map((gap) => gap.elementId)).toEqual(['APP@heavy', 'APP@light'])
  })

  it('breaks ties by id so the list does not shuffle between reloads', () => {
    const gaps = structuralGaps([
      issue({ node_id: 'APP@b', witness: ['w'] }),
      issue({ node_id: 'APP@a', witness: ['w'] }),
    ])

    expect(gaps.map((gap) => gap.elementId)).toEqual(['APP@a', 'APP@b'])
  })

  it('carries the witness through, since the claim is otherwise unverifiable', () => {
    expect(structuralGaps([issue()])[0].witness).toHaveLength(1)
  })

  it('survives a finding that carried no witness', () => {
    expect(structuralGaps([issue({ witness: undefined as unknown as string[] })])[0].witness)
      .toEqual([])
  })
})

describe('gapSummary', () => {
  it('counts them and says how they are ordered, rather than presenting a backlog', () => {
    const summary = gapSummary(structuralGaps([issue()]))

    expect(summary).toContain('1 load-bearing element')
    expect(summary).not.toContain('outstanding')
  })

  it('states the covered case positively rather than showing an empty list', () => {
    expect(gapSummary([])).toContain('has been reached')
  })
})


// ── Naming the element a finding is about ─────────────────────────────────────
// The list showed a hundred bare artifact ids, each followed by a sentence repeating the id — so the
// one thing a reader needed, *which element this is*, was the one thing missing.

describe('typeAbbreviation', () => {
  it('reads the type off the id, which already carries it', () => {
    expect(typeAbbreviation('REQ@1777369067.3cJ1Yi')).toBe('REQ')
  })

  it('has nothing to report for an id with no prefix', () => {
    expect(typeAbbreviation('not-an-artifact-id')).toBe('')
  })
})

describe('gapHeading', () => {
  it('leads with the type and name, and demotes the id', () => {
    expect(gapHeading('REQ@1777369067.3cJ1Yi', 'Write composable code')).toEqual({
      heading: 'REQ: Write composable code',
      subheading: 'REQ@1777369067.3cJ1Yi',
    })
  })

  it('falls back to the id when the model cannot describe the element', () => {
    /* Honest: inventing a label for an element nothing can describe is worse than showing its id. */
    expect(gapHeading('REQ@1', '')).toEqual({ heading: 'REQ@1', subheading: '' })
    expect(gapHeading('REQ@1', '   ')).toEqual({ heading: 'REQ@1', subheading: '' })
  })

  it('never drops the id, only demotes it', () => {
    expect(gapHeading('REQ@1', 'Something').subheading).toBe('REQ@1')
  })
})

describe('structuralGaps naming', () => {
  it('carries the heading and the demoted id per gap', () => {
    const gaps = structuralGaps([issue({ subject_name: 'Shared provider' })])

    expect(gaps[0].heading).toBe('APP: Shared provider')
    expect(gaps[0].subheading).toBe('APP@one')
  })

  it('still renders a finding from a response that carried no name', () => {
    expect(structuralGaps([issue()])[0].heading).toBe('APP@one')
  })
})

describe('GAPS_EXPLANATION', () => {
  it('says what these elements are and what to do about them', () => {
    /* The panel asks a reader to act on a claim the *graph* made and they did not, so it has to
       explain itself or be ignored — which is what happened. */
    expect(GAPS_EXPLANATION).toContain('depend on')
    expect(GAPS_EXPLANATION).toContain('control structure')
    expect(GAPS_EXPLANATION.length).toBeGreaterThan(120)
  })

  it('claims nothing about elements standing in for one another', () => {
    /* The model never says that. The withdrawn `sole_providers` reason did, and it measured how
       sparsely a neighbourhood was drawn rather than whether an alternative exists. */
    expect(GAPS_EXPLANATION.toLowerCase()).not.toContain('stand in')
  })
})
