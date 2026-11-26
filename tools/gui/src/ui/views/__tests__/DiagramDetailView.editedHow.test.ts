/**
 * How a diagram's page offers editing: a diagram of this engagement whose type the catalogue says is arranged on
 * the canvas is edited there; the same diagram written by hand is offered *Lay out automatically…* instead, and
 * nothing else is — whatever its type is called.
 */
import { describe, expect, it } from 'vitest'
import { editsOnCanvas, offersAutomaticLayout } from '../DiagramDetailView.helpers'

const diagram = (diagram_type: string, is_global = false, manual = false, drawnByHand = false) =>
  ({ diagram_type, is_global, extra: manual ? { 'manual-layout': true } : {},
    ...(drawnByHand ? { written_by_hand: 'it draws what a generated picture would not: boxes "Team A"' } : {}) })
/** What the catalogue says of each type here: the ArchiMate views arrange, others do not. */
const arranges = (detail: { readonly diagram_type: string }): boolean => detail.diagram_type.startsWith('archimate')

describe('how a diagram is edited', () => {
  it.each([
    ['an ArchiMate diagram', diagram('archimate-layered'), true, false],
    ['one written by hand', diagram('archimate-layered', false, true), false, true],
    ['one drawn by hand without the flag', diagram('archimate-layered', false, false, true), true, true],
    ['an enterprise one', diagram('archimate-layered', true, true), false, false],
    ['another kind', diagram('c4-context', false, true), false, false],
  ])('%s: on its canvas %s, offered automatic layout %s', (_case, detail, canvas, offered) => {
    expect(editsOnCanvas(detail, arranges(detail))).toBe(canvas)
    expect(offersAutomaticLayout(detail, arranges(detail))).toBe(offered)
  })

  it('reads the catalogue, not the name: a type called archimate that does not arrange is not arranged', () => {
    expect(editsOnCanvas(diagram('archimate-layered'), false)).toBe(false)
    expect(editsOnCanvas(diagram('some-notation'), true)).toBe(true)
  })

  it('offers nothing before the diagram is read', () => {
    expect(editsOnCanvas(null, true)).toBe(false)
    expect(offersAutomaticLayout(null, true)).toBe(false)
  })
})
