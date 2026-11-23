/**
 * View mode and edit mode on a diagram's own page (D15): entering, the keys, and the ways out.
 *
 * - **Escape steps outward** (owner, F1), wherever focus is on the page: an open list of changes, then
 *   the leave choice, then the selection, then edit mode itself — which leaves at once when nothing
 *   is unsaved, and otherwise asks, in the edit bar, *Save and exit*, *Discard and exit* or *Keep
 *   editing* (Q2). A text field keeps its own Escape.
 * - **Done** is the same last step.
 * - **Save** is one press and stays in edit mode (Q4); **Discard** returns to the last save.
 * - **Space held** turns a press on the canvas into a pan; the wheel zooms as in view mode.
 * - The first move of an automatically laid-out picture takes it over (D16): said once, in a toast.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Ref } from 'vue'
import type { ModelService } from '../../application/ModelService'
import { SMALLEST_ELEMENT, moved, resized, resizedExtent } from '../../domain/layout/lab/labArrangement'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import { useDiagramEditing } from './useDiagramEditing'

/** How far an arrow moves or resizes a shape: the grid, or one pixel with Shift. */
const GRID = 8

/** Each arrow key as the direction it moves in, read by the character it produces, not its position. */
const ARROWS: Readonly<Record<string, readonly [number, number]>> = {
  ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
}

/** What the page's canvas and edit bar let the keys ask of them. */
export interface CanvasHandle {
  readonly selected: string | null
  readonly hasSelection: boolean
  readonly clearSelection: () => void
}
export interface EditBarHandle {
  readonly closeList: () => boolean
}

type Toast = (message: string, type?: 'info' | 'warn' | 'error', durationMs?: number) => void

const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement
  && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

export function useDiagramEditMode(
  svc: ModelService,
  diagramId: Ref<string>,
  parts: { canvas: Ref<CanvasHandle | null>; bar: Ref<EditBarHandle | null>; membership: () => DrawnMembership | null },
  onLeft: () => void,
  toast: Toast,
) {
  const editing = useDiagramEditing(svc, () => diagramId.value, parts.membership, onLeft)
  const active = ref(false)
  const leaving = ref(false)
  const spaceHeld = ref(false)
  const told = new Set<string>()
  const session = editing.session

  const enter = async () => {
    leaving.value = false
    if (await editing.open()) active.value = true
    else {
      const why = editing.error.value ?? 'its picture could not be read'
      toast(`This diagram cannot be arranged here: ${why}`, 'error')
    }
  }

  const exit = () => {
    active.value = false
    leaving.value = false
    onLeft()
  }

  /** Done, or Escape with nothing else to close: leave, or ask how when something is unsaved. */
  const done = () => {
    if (editing.changes.value.length === 0) exit()
    else leaving.value = true
  }

  const saveAndExit = async () => { if (await editing.save()) exit() }
  const discardAndExit = () => { editing.discard(); exit() }
  const keepEditing = () => { leaving.value = false }

  const escape = () => {
    if (parts.bar.value?.closeList()) return
    if (leaving.value) return keepEditing()
    if (parts.canvas.value?.hasSelection) return parts.canvas.value.clearSelection()
    done()
  }

  /**
   * The selected shape moved by the arrows, or resized by Alt and the arrows from its right and bottom
   * edges (Q35): one undoable step each, *by* pixels at a time.
   */
  const nudge = (alias: string, [x, y]: readonly [number, number], by: number, resize: boolean) => {
    const geometry = session.geometry.value
    if (!geometry) return
    session.begin()
    const from = session.arrangement.value
    const placement = session.placement.value
    const extent = placement?.elements.get(alias) ?? placement?.boxes.get(alias)
    if (!from || !extent) return
    const isBox = placement?.boxes.has(alias) ?? false
    const next = resize
      ? resized(geometry, from, alias, resizedExtent(extent, 'se', x * by, y * by, isBox ? 1 : SMALLEST_ELEMENT))
      : moved(geometry, from, alias, x * by, y * by)
    session.preview(next, new Set([alias]))
    session.commit()
  }

  const onKey = (event: KeyboardEvent) => {
    if (!active.value || isTyping(event.target)) return
    const command = event.ctrlKey || event.metaKey
    const key = event.key.toLowerCase()
    if (event.key === 'Escape') {
      event.preventDefault()
      escape()
    } else if (command && key === 'z') {
      event.preventDefault()
      if (event.shiftKey) session.redo()
      else session.undo()
    } else if (command && key === 'y') {
      event.preventDefault()
      session.redo()
    } else if ((event.key === 'Delete' || event.key === 'Backspace') && parts.canvas.value?.selected) {
      // Remove from the diagram only (owner's standing rule); deleting from the model is a menu command.
      event.preventDefault()
      editing.remove(parts.canvas.value.selected)
      parts.canvas.value.clearSelection()
    } else if (event.key in ARROWS && parts.canvas.value?.selected) {
      event.preventDefault()
      nudge(parts.canvas.value.selected, ARROWS[event.key], event.shiftKey ? 1 : GRID, event.altKey)
    } else if (event.key === ' ') {
      event.preventDefault()
      spaceHeld.value = true
    }
  }
  const onKeyUp = (event: KeyboardEvent) => { if (event.key === ' ') spaceHeld.value = false }

  /** A press on the canvas pans only while Space is held: otherwise it is the canvas's to select and move. */
  const panPress = (event: MouseEvent, pan: (event: MouseEvent) => void) => {
    if (spaceHeld.value) pan(event)
  }

  // Said once per diagram, at the moment it happens: the picture is now arranged by hand.
  watch(() => session.state.value?.byHand, (byHand, was) => {
    if (!active.value || !byHand || was !== false || told.has(diagramId.value)) return
    if (session.history.value.length === 0) return
    told.add(diagramId.value)
    toast(
      'Arranged by hand from here on. Undo, or “Return to automatic”, gives the automatic layout back.',
      'info', 6000,
    )
  })

  // Leaving the page with the session open leaves nothing behind.
  watch(diagramId, () => { active.value = false; leaving.value = false })

  onMounted(() => {
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onKeyUp)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKey)
    window.removeEventListener('keyup', onKeyUp)
  })

  return {
    editing, session, active, leaving, spaceHeld,
    canUndo: computed(() => session.history.value.length > 0),
    canRedo: computed(() => session.future.value.length > 0),
    enter, done, saveAndExit, discardAndExit, keepEditing, panPress,
  }
}

export type DiagramEditMode = ReturnType<typeof useDiagramEditMode>
