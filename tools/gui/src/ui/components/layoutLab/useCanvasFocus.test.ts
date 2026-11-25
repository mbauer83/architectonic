/**
 * The edit canvas's element focus (sketch 01·3, 02·9): Enter goes in to the first shape, Tab walks the
 * reading order selecting each and leaves past the last, Shift+Enter toggles, an arrow moves the focus
 * to the nearest element without selecting, Ctrl+A selects every element, and the ring shows only for
 * the keyboard and not on a shape that is the whole selection.
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { Effect } from 'effect'
import type { Extent } from '../../../domain/layout/geometry'
import { SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import { useArrangementSession } from '../../composables/useArrangementSession'
import { useCanvasFocus } from './useCanvasFocus'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

/** Box G holds A and B side by side; C sits below on its own. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 600, 400), backdrop: [],
  elements: [
    { alias: 'B', label: 'Bravo', extent: at(140, 40, 240, 80), inside: 'G', words: [], drawing: SHAPE_DRAWING },
    { alias: 'A', label: 'Alpha', extent: at(20, 40, 120, 80), inside: 'G', words: [], drawing: SHAPE_DRAWING },
    { alias: 'C', label: 'Charlie', extent: at(20, 200, 120, 240), words: [], drawing: SHAPE_DRAWING },
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', label: 'Group', extent: at(10, 10, 250, 90),
    words: [], drawing: SHAPE_DRAWING,
  }],
  relations: [],
}

const opened = () => {
  const session = useArrangementSession(() => Effect.succeed([]), (_drawn, automatic) => automatic)
  session.open(geometry)
  const selection = ref<readonly string[]>([])
  return { selection, focus: useCanvasFocus(session, { selection }) }
}

describe('the element focus of the edit canvas', () => {
  it('goes in on Enter to the first shape in reading order, a box before its members', () => {
    const { selection, focus } = opened()
    focus.enter(false)
    expect([focus.focused.value, selection.value]).toEqual(['G', ['G']])
    expect(focus.announced.value).toBe('Group, box, selected, 1 of 4')
  })

  it('walks with Tab and Shift+Tab, selecting each, and leaves past the last', () => {
    const { selection, focus } = opened()
    expect(focus.step(true)).toBe(false)
    focus.enter(false)
    expect([focus.step(true), focus.step(true), focus.step(true)]).toEqual([true, true, true])
    expect([focus.focused.value, selection.value]).toEqual(['C', ['C']])
    expect(focus.step(false)).toBe(true)
    expect(focus.focused.value).toBe('B')
    focus.step(true)
    expect(focus.step(true)).toBe(false)
    expect(focus.focused.value).toBeNull()
  })

  it('toggles the focused shape with Shift+Enter, and selects it alone with Enter', () => {
    const { selection, focus } = opened()
    focus.pointed('A')
    focus.enter(true)
    focus.pointed('C')
    focus.enter(true)
    expect(selection.value).toEqual(['A', 'C'])
    focus.enter(true)
    expect(selection.value).toEqual(['A'])
    focus.enter(false)
    expect(selection.value).toEqual(['C'])
  })

  it('moves the focus to the nearest element by arrow, selecting nothing; false without a focus', () => {
    const { selection, focus } = opened()
    expect(focus.towards({ x: 1, y: 0 })).toBe(false)
    focus.pointed('A')
    expect(focus.towards({ x: 1, y: 0 })).toBe(true)
    expect([focus.focused.value, selection.value]).toEqual(['B', []])
    focus.towards({ x: 0, y: 1 })
    expect(focus.focused.value).toBe('C')
  })

  it('selects every element with Ctrl+A', () => {
    const { selection, focus } = opened()
    focus.selectAll()
    expect([...selection.value].sort()).toEqual(['A', 'B', 'C'])
  })

  it('rings the keyboard focus, never the pointer’s, nor a shape that is the whole selection', () => {
    const { focus } = opened()
    focus.pointed('A')
    expect(focus.ring.value).toBeNull()
    focus.towards({ x: 1, y: 0 })
    expect(focus.ring.value).toEqual(at(140, 40, 240, 80))
    focus.enter(false)
    expect(focus.ring.value).toBeNull()
  })
})
