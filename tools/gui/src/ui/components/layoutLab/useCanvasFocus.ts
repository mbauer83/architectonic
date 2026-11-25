/**
 * The element focus of the canvas in edit mode (sketch 01·3, 02·9; Q8, Q9): which shape the keyboard is
 * on, apart from what is selected.
 *
 * The canvas is one Tab stop; Enter or an arrow goes in. Then Tab and Shift+Tab walk the shapes in
 * reading order, a box just before its first member, selecting each, and past the last Tab leaves.
 * Enter selects the focused shape and Shift+Enter toggles it; with nothing selected an arrow moves the
 * focus to the nearest element that way. A press on a shape puts the focus on it; a press on empty paper
 * that clears the selection clears the focus with it. The focus ring is drawn only while the keyboard
 * is in use, and not on a shape that is already the whole selection.
 */
import { computed, ref, watch, type Ref } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { type Stop, nearestTowards, walkOrder } from '../../../domain/layout/keyboardReach'
import type { ArrangementSession } from '../../composables/useArrangementSession'

/** What the focus reads of the gesture: the selection, which it sets. */
interface Selecting {
  readonly selection: Ref<readonly string[]>
}

/** *isDraft*: whether a shape draws a draft, which it is announced as (sketch 03·4). */
export function useCanvasFocus(
  session: ArrangementSession, gesture: Selecting, isDraft: (alias: string) => boolean = () => false,
) {
  const focused = ref<string | null>(null)
  /** Whether the keyboard moved the focus last, rather than the pointer: the ring shows only then. */
  const byKeyboard = ref(false)

  const stops = computed((): { elements: Stop[]; boxes: Stop[] } => {
    const where = session.placement.value
    return {
      elements: where ? [...where.elements].map(([id, box]) => ({ id, box })) : [],
      boxes: where ? [...where.boxes].map(([id, box]) => ({ id, box })) : [],
    }
  })
  const order = computed((): string[] => {
    const drawn = session.geometry.value
    const inside = new Map([...drawn?.elements ?? [], ...drawn?.boxes ?? []].map((one) => [one.alias, one.inside]))
    return walkOrder(stops.value.elements, stops.value.boxes, (id) => inside.get(id))
  })
  const extentOf = (alias: string | null): Extent | null => {
    const where = session.placement.value
    return alias === null || !where ? null : where.elements.get(alias) ?? where.boxes.get(alias) ?? null
  }

  const focusOn = (alias: string, select: boolean) => {
    focused.value = alias
    byKeyboard.value = true
    if (select) gesture.selection.value = [alias]
  }

  /** Tab or Shift+Tab: the next shape in reading order; answers false where Tab leaves the canvas. */
  const step = (forward: boolean): boolean => {
    if (focused.value === null) return false
    const next = order.value[order.value.indexOf(focused.value) + (forward ? 1 : -1)]
    if (next === undefined) {
      focused.value = null
      return false
    }
    focusOn(next, true)
    return true
  }

  /** Enter goes in to the first shape; on a shape, selects it, or with *toggle* adds or takes it out. */
  const enter = (toggle: boolean) => {
    const at = focused.value
    if (at === null) {
      if (order.value.length > 0) focusOn(order.value[0], true)
      return
    }
    byKeyboard.value = true
    const selection = gesture.selection.value
    gesture.selection.value = !toggle ? [at]
      : selection.includes(at) ? selection.filter((one) => one !== at) : [...selection, at]
  }

  /** An arrow with nothing selected: the focus to the nearest element that way; false with no focus. */
  const towards = (direction: { readonly x: number; readonly y: number }): boolean => {
    const from = extentOf(focused.value)
    if (!from) return false
    const next = nearestTowards(from, stops.value.elements.filter((stop) => stop.id !== focused.value), direction)
    if (next) focusOn(next.id, false)
    return true
  }

  /** Ctrl+A: every element. */
  const selectAll = () => { gesture.selection.value = stops.value.elements.map((stop) => stop.id) }

  /** A press on a shape puts the focus there, one on the paper takes it away; the pointer draws no ring. */
  const pointed = (alias: string | null) => {
    focused.value = alias
    byKeyboard.value = false
  }
  const clear = () => { focused.value = null }
  watch(() => gesture.selection.value.length, (count) => { if (count === 0 && !byKeyboard.value) clear() })

  /** Where the focus ring is drawn, or null: keyboard focus on a shape that is not the whole selection. */
  const ring = computed((): Extent | null => {
    const selection = gesture.selection.value
    const sole = selection.length === 1 && selection[0] === focused.value
    return byKeyboard.value && !sole ? extentOf(focused.value) : null
  })

  /** The focused shape as it is announced: its name, a box said as such, and its place in the order. */
  const announced = computed((): string => {
    const at = focused.value
    const drawn = session.geometry.value
    if (at === null || !drawn) return ''
    const box = drawn.boxes.find((one) => one.alias === at)
    const name = box?.label ?? drawn.elements.find((one) => one.alias === at)?.label ?? at
    const selected = gesture.selection.value.includes(at) ? ', selected' : ''
    const draft = isDraft(at) ? ', draft' : ''
    return `${name}${box ? ', box' : ''}${draft}${selected}, ${order.value.indexOf(at) + 1} of ${order.value.length}`
  })

  return {
    focused, ring, announced, extent: computed(() => extentOf(focused.value)),
    step, enter, towards, selectAll, pointed, clear,
  }
}

export type CanvasFocus = ReturnType<typeof useCanvasFocus>
