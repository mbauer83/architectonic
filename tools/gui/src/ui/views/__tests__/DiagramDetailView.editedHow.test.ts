/**
 * How a diagram's page offers editing: an ArchiMate diagram of this engagement is arranged on its canvas;
 * the same diagram written by hand is offered *Lay out automatically…* instead, and nothing else is.
 */
import { describe, expect, it } from 'vitest'
import { editsOnCanvas, offersAutomaticLayout } from '../DiagramDetailView.helpers'

const diagram = (diagram_type: string, is_global = false, manual = false) =>
  ({ diagram_type, is_global, extra: manual ? { 'manual-layout': true } : {} })

describe('how a diagram is edited', () => {
  it.each([
    ['an ArchiMate diagram', diagram('archimate-layered'), true, false],
    ['one written by hand', diagram('archimate-layered', false, true), false, true],
    ['an enterprise one', diagram('archimate-layered', true, true), false, false],
    ['another kind', diagram('c4-context', false, true), false, false],
  ])('%s: on its canvas %s, offered automatic layout %s', (_case, detail, canvas, offered) => {
    expect(editsOnCanvas(detail)).toBe(canvas)
    expect(offersAutomaticLayout(detail)).toBe(offered)
  })

  it('offers nothing before the diagram is read', () => {
    expect(editsOnCanvas(null)).toBe(false)
    expect(offersAutomaticLayout(null)).toBe(false)
  })
})
