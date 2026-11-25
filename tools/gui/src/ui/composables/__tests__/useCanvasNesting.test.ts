// @vitest-environment jsdom
/**
 * Dropping an element on another asks whether to make it part of that one (03·10); *Don't nest* puts it
 * back where the drag started, as one step Undo takes back, leaving the session as it was before the
 * drop. Opened from the menu instead, *Don't nest* only closes the question.
 */
import { describe, expect, it, vi } from 'vitest'
import { computed, effectScope, nextTick, ref } from 'vue'
import { Effect } from 'effect'
import type { Extent } from '../../../domain/layout/geometry'
import { moved } from '../../../domain/layout/lab/labArrangement'
import { SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import { useArrangementSession } from '../useArrangementSession'
import type { CanvasPopoverLevel } from '../useCanvasPopover'
import { useCanvasNesting } from '../useCanvasNesting'
import type { DiagramEditing } from '../useDiagramEditing'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, extent: Extent) => ({
  alias, key: `APP@1.${alias}`, label: alias, extent, inside: undefined, words: [], outside_label: undefined,
  drawing: SHAPE_DRAWING,
})
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 700, 500), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [element('A', at(20, 40, 120, 80)), element('B', at(400, 240, 500, 280))],
  boxes: [], relations: [],
}

const nesting = () => {
  const session = useArrangementSession(() => Effect.succeed([]), (_drawn, automatic) => automatic)
  session.open(geometry)
  const mode = ref<CanvasPopoverLevel | null>(null)
  const close = vi.fn(() => { mode.value = null })
  const editing = { session, error: ref(null) } as unknown as DiagramEditing
  const members = computed(() => geometry.elements
    .map((one) => ({ alias: one.alias, id: one.key ?? one.alias, name: one.label })))
  const scope = effectScope()
  const used = scope.run(() => useCanvasNesting(
    editing, ref(null), ref(''), members, { mode, error: ref(''), position: () => {}, close }, () => {},
  ))!
  return { session, mode, close, used }
}

describe("Don't nest", () => {
  it('after a drop on an element, returns the element to where the drag started, as one undoable step', async () => {
    const { session, mode, used } = nesting()
    const started = session.state.value
    // The drag's own step: A dropped onto B.
    session.change((drawn, now) => moved(drawn, now, 'A', 390, 210))
    used.dropped('A', 'B', 0, 0)
    expect(mode.value).toBe('nest')
    expect(used.asked.value).toBe('B')

    used.dontNest()
    await nextTick()
    expect(mode.value).toBeNull()
    expect(session.arrangement.value?.elements.get('A')).toEqual(started?.arrangement.elements.get('A'))
    expect(session.state.value?.byHand).toBe(started?.byHand)
    // Undo takes the return back: the element is where it was dropped again.
    session.undo()
    expect(session.arrangement.value?.elements.get('A')).toEqual(at(410, 250, 510, 290))
  })

  it('opened from the menu, only closes the question and changes nothing', () => {
    const { session, mode, close, used } = nesting()
    mode.value = 'nest'
    const before = session.state.value
    used.dontNest()
    expect(close).toHaveBeenCalledWith(true)
    expect(session.state.value).toBe(before)
    expect(session.history.value).toHaveLength(0)
  })
})
