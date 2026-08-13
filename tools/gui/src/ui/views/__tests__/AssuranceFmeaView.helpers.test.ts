/**
 * The matrix's display rules — the ones that decide whether a reader draws the right conclusion.
 *
 * Every test here corresponds to a way of rendering the grid that still looks plausible and is
 * wrong: an unrated cell painted like a low-priority one, an unexamined cell indistinguishable from
 * a dismissed one, an occurrence field offered where the answer cannot matter, or a worklist
 * ordered by something presented as a score.
 */

import { describe, expect, it } from 'vitest'
import {
  basisGlyph,
  basisTooltip,
  cellClass,
  cellLabel,
  coverageLine,
  guidewordLabel,
  visibleFactors,
  worklistOrder,
  awaitsOccurrence,
  isRecordingCell,
  occurrenceBasisDigest,
  elementHeading,
  elementRoute,
} from '../AssuranceFmeaView.helpers'
import type { CellView, RowView } from '../AssuranceFmeaView.helpers'
import { entityDetailRoute } from '../../router/artifactRoutes'

function cell(overrides: Partial<CellView> = {}): CellView {
  return {
    guideword: 'no-function',
    state: 'recorded',
    node_id: 'FMD@1',
    action_priority: 'medium',
    occurrence_is_requested: true,
    next_action: '',
    // Both fields, empty: the route sends a dismissal on every cell, not only a dismissed one.
    dismissal: { by: '', reason: '' },
    factors: {
      severity: { value: 'major', basis: 'derived', basis_digest: 'sev-1', assessment: null, superseded: null },
      occurrence: { value: null, basis: 'absent', basis_digest: 'occ-1', assessment: null, superseded: null },
      detectability: { value: 'low', basis: 'derived', basis_digest: 'det-1', assessment: null, superseded: null },
    },
    occurrence_rationale_draft: '- nothing can stand in for it',
    ...overrides,
  }
}

function row(overrides: Partial<RowView> = {}): RowView {
  return {
    element_id: 'APP@one',
    // Always sent, empty when the architecture model cannot describe the element — which the view's
    // own type had declared optional, so an absent name and an undescribable one read alike.
    element_name: '',
    element_type: '',
    nominated_by: ['control-structure'],
    cells: [cell()],
    answered_cells: 1,
    unanswered_cells: 4,
    worst_action_priority: 'medium',
    ...overrides,
  }
}

describe('an unrated cell never reads as a quiet one', () => {
  it('indeterminate gets a class of its own', () => {
    const painted = cellClass(cell({ action_priority: 'indeterminate' }))

    expect(painted).toContain('cell-indeterminate')
    expect(painted).not.toContain('cell-low')
  })

  it('and says it is unrated rather than showing a band name', () => {
    expect(cellLabel(cell({ action_priority: 'indeterminate' }))).toBe('Not yet rated')
  })

  it('while a real low band is labelled as such', () => {
    expect(cellLabel(cell({ action_priority: 'low' }))).toBe('low')
    expect(cellClass(cell({ action_priority: 'low' }))).toContain('cell-low')
  })
})

describe('the three cell states are distinguishable', () => {
  it('untouched, not-credible and recorded each paint differently', () => {
    const classes = new Set([
      cellClass(cell({ state: 'untouched' })),
      cellClass(cell({ state: 'not-credible' })),
      cellClass(cell({ state: 'recorded', action_priority: 'low' })),
    ])

    expect(classes.size).toBe(3)
  })

  it('an unexamined cell says so rather than being blank', () => {
    // A blank cell is exactly the ambiguity three states exist to remove.
    expect(cellLabel(cell({ state: 'untouched' }))).toBe('Not examined')
  })

  it('a dismissed cell reads as examined, not as empty', () => {
    expect(cellLabel(cell({ state: 'not-credible' }))).toBe('Not credible')
  })
})

describe('occurrence is only offered where it could matter', () => {
  it('the field is omitted when the band is already settled', () => {
    const shown = visibleFactors(cell({ occurrence_is_requested: false }))

    expect(shown).not.toContain('occurrence')
    expect(shown).toEqual(['severity', 'detectability'])
  })

  it('and offered when it is decisive', () => {
    expect(visibleFactors(cell({ occurrence_is_requested: true }))).toContain('occurrence')
  })
})

describe('every value says where it came from', () => {
  it('derived, asserted and superseded each have their own glyph', () => {
    const glyphs = new Set([
      basisGlyph('derived'),
      basisGlyph('asserted'),
      basisGlyph('derived-superseding-an-assessment'),
      basisGlyph('absent'),
    ])

    expect(glyphs.size).toBe(4)
  })

  it('a superseded judgement is explained, including what it used to say', () => {
    const tooltip = basisTooltip('severity', {
      value: 'major',
      basis: 'derived-superseding-an-assessment',
      basis_digest: 'sev-2',
      assessment: null,
      superseded: { value: 'minor', author: 'analyst', justification: 'reviewed at the time' },
    })

    expect(tooltip).toContain('the model has changed')
    expect(tooltip).toContain('minor')
    expect(tooltip).toContain('analyst')
  })

  it('an asserted value says who decided it and why, not merely that a person did', () => {
    const tooltip = basisTooltip('occurrence', {
      value: 'unlikely',
      basis: 'asserted',
      basis_digest: 'occ-1',
      assessment: {
        value: 'unlikely',
        author: 'analyst',
        justification: 'one report in two years of operation',
      },
      superseded: null,
    })

    expect(tooltip).toContain('analyst')
    expect(tooltip).toContain('one report in two years of operation')
  })

  it('a derived value claims no author, because nobody asserted it', () => {
    const tooltip = basisTooltip('severity', {
      value: 'major', basis: 'derived', basis_digest: 'sev-1', assessment: null, superseded: null,
    })

    expect(tooltip).toBe('severity is derived from the model')
  })

  it('the basis lives in a glyph and its tooltip, not in a column of prose', () => {
    expect(basisGlyph('derived').length).toBeLessThanOrEqual(2)
  })
})

describe('the worklist is ordered, never scored', () => {
  it('the worst band comes first', () => {
    const ordered = worklistOrder([
      row({ element_id: 'APP@low', worst_action_priority: 'low' }),
      row({ element_id: 'APP@high', worst_action_priority: 'high' }),
    ])

    expect(ordered[0].element_id).toBe('APP@high')
  })

  it('an unrated element does not outrank a real finding', () => {
    const ordered = worklistOrder([
      row({ element_id: 'APP@unrated', worst_action_priority: null }),
      row({ element_id: 'APP@low', worst_action_priority: 'low' }),
    ])

    expect(ordered[0].element_id).toBe('APP@low')
  })

  it('within a band, the least examined comes first', () => {
    const ordered = worklistOrder([
      row({ element_id: 'APP@done', worst_action_priority: 'high', unanswered_cells: 0 }),
      row({ element_id: 'APP@open', worst_action_priority: 'high', unanswered_cells: 3 }),
    ])

    expect(ordered[0].element_id).toBe('APP@open')
  })

  it('the order is stable for otherwise identical rows', () => {
    const ordered = worklistOrder([
      row({ element_id: 'APP@b' }),
      row({ element_id: 'APP@a' }),
    ])

    expect(ordered.map((r) => r.element_id)).toEqual(['APP@a', 'APP@b'])
  })

  it('does not mutate what it was given', () => {
    const rows = [row({ element_id: 'APP@b' }), row({ element_id: 'APP@a' })]

    worklistOrder(rows)

    expect(rows[0].element_id).toBe('APP@b')
  })
})

describe('coverage counts a dismissal as an answer', () => {
  it('so a finished matrix looks finished', () => {
    const line = coverageLine([row({ answered_cells: 5, cells: Array.from({ length: 5 }, () => cell()) })])

    expect(line).toBe('5 of 5 cells answered across 1 element(s)')
  })

  it('and an empty candidate set says so rather than reporting nothing', () => {
    expect(coverageLine([])).toBe('No candidate elements yet')
  })
})

describe('guideword headings', () => {
  it('read as language rather than as slugs', () => {
    expect(guidewordLabel('partial-function')).toBe('Partial or degraded')
  })

  it('fall back to the slug for one this build does not know', () => {
    expect(guidewordLabel('teleportation-failure')).toBe('teleportation-failure')
  })
})

describe('awaitsOccurrence', () => {
  it('is true for a recorded cell whose occurrence is asked for and not yet judged', () => {
    expect(awaitsOccurrence(cell())).toBe(true)
  })

  it('is false where occurrence could not change the band, so the field is not offered', () => {
    expect(awaitsOccurrence(cell({ occurrence_is_requested: false }))).toBe(false)
  })

  it('is false once a judgement has been recorded', () => {
    // Rebuilt rather than mutated: the decoded factor map is readonly, as decoded data should be.
    const judged = cell({
      factors: {
        ...cell().factors,
        occurrence: {
          value: 'occasional', basis: 'asserted', basis_digest: 'occ-1', assessment: null, superseded: null,
        },
      },
    })

    expect(awaitsOccurrence(judged)).toBe(false)
  })

  it('is false for an untouched cell — there is no failure mode to judge yet', () => {
    expect(awaitsOccurrence(cell({ state: 'untouched', node_id: null }))).toBe(false)
  })

  it('is false for a dismissal, which is already an answer', () => {
    expect(awaitsOccurrence(cell({ state: 'not-credible' }))).toBe(false)
  })
})

describe('occurrenceBasisDigest', () => {
  it('is the digest the judgement must be filed against', () => {
    expect(occurrenceBasisDigest(cell())).toBe('occ-1')
  })
})

describe('isRecordingCell', () => {
  it('opens the recorder on the cell whose failure mode was chosen', () => {
    expect(isRecordingCell('FMD@1', cell())).toBe(true)
  })

  it('leaves every other cell closed', () => {
    expect(isRecordingCell('FMD@1', cell({ node_id: 'FMD@2' }))).toBe(false)
  })

  it('opens nothing when nothing has been chosen', () => {
    expect(isRecordingCell(null, cell())).toBe(false)
  })

  it('does not treat an un-examined cell as the open one', () => {
    // A bare `openNodeId === cell.node_id` matches null against null, which would open a
    // recorder on every cell that has no failure mode as soon as the matrix loads.
    expect(isRecordingCell(null, cell({ state: 'untouched', node_id: null }))).toBe(false)
  })

  it('keeps un-examined cells closed while another cell is being recorded', () => {
    expect(isRecordingCell('FMD@1', cell({ state: 'untouched', node_id: null }))).toBe(false)
  })
})



// ── Naming a row's element ────────────────────────────────────────────────────
// The row used to show the bare artifact id, which is the one label that says nothing about which
// element an analyst is being asked to assess — and a hundred of them down the side read as noise.

describe('elementHeading', () => {
  it('leads with the type and name, and demotes the id', () => {
    const heading = elementHeading(row({
      element_id: 'APP@1712870400.abc123.credential-backend',
      element_type: 'application-component',
      element_name: 'Credential Backend',
    }))

    expect(heading.primary).toBe('application-component: Credential Backend')
    expect(heading.secondary).toBe('APP@1712870400.abc123.credential-backend')
  })

  it('never drops the id, only demotes it', () => {
    /* It is what an analyst quotes in a review and what every other surface keys on. */
    const heading = elementHeading(row({
      element_id: 'APP@1', element_type: 'node', element_name: 'Key store',
    }))

    expect(heading.secondary).toBe('APP@1')
  })

  it('falls back to the id when the architecture model cannot describe the element', () => {
    /* The empty basis is the honest answer when no model is loaded; inventing a label for an
       element nothing can describe would be worse than showing its id. */
    const heading = elementHeading(row({ element_id: 'APP@1' }))

    expect(heading.primary).toBe('APP@1')
    expect(heading.secondary).toBe('')
  })

  it('shows the name alone when the type is unknown', () => {
    const heading = elementHeading(row({ element_id: 'APP@1', element_name: 'Key store' }))

    expect(heading.primary).toBe('Key store')
    expect(heading.secondary).toBe('APP@1')
  })

  it('treats a blank name as no name rather than rendering an empty heading', () => {
    const heading = elementHeading(row({
      element_id: 'APP@1', element_name: '   ', element_type: 'node',
    }))

    expect(heading.primary).toBe('APP@1')
  })
})

// ── Reaching the element a row is about ───────────────────────────────────────
// The heading names a real model element, so it links to it: reading a failure mode and then
// having to search for the component it belongs to is the dead end the matrix exists to remove.

describe('elementRoute', () => {
  it('routes a row to its architecture element', () => {
    expect(elementRoute(row({ element_id: 'APP@1712870400.abc123.credential-backend' })))
      .toBe(entityDetailRoute('APP@1712870400.abc123.credential-backend'))
  })

  it('routes a short-form id, which is the form a binding stores', () => {
    expect(elementRoute(row({ element_id: 'APP@1777293133.OYEmP1' })))
      .toBe(entityDetailRoute('APP@1777293133.OYEmP1'))
  })

  it('is null when the row names no artifact, rather than linking nowhere', () => {
    expect(elementRoute(row({ element_id: 'some free-text element' }))).toBeNull()
    expect(elementRoute(row({ element_id: '' }))).toBeNull()
  })
})
