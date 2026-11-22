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
import { useDiagramEditing } from './useDiagramEditing'

/** What the page's canvas and edit bar let the keys ask of them. */
export interface CanvasHandle {
  readonly hasSelection: boolean
  readonly clearSelection: () => void
}
export interface EditBarHandle {
  readonly closeList: () => boolean
}

type Toast = (message: string, type?: 'info' | 'warn' | 'error', durationMs?: number) => void

const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

export function useDiagramEditMode(
  svc: ModelService,
  diagramId: Ref<string>,
  parts: { canvas: Ref<CanvasHandle | null>; bar: Ref<EditBarHandle | null> },
  onLeft: () => void,
  toast: Toast,
) {
  const editing = useDiagramEditing(svc, () => diagramId.value)
  const active = ref(false)
  const leaving = ref(false)
  const spaceHeld = ref(false)
  const told = new Set<string>()
  const session = editing.session

  const enter = async () => {
    leaving.value = false
    if (await editing.open()) active.value = true
    else toast(`This diagram cannot be arranged here: ${editing.error.value ?? 'its picture could not be read'}`, 'error')
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
    toast('Arranged by hand from here on. Undo, or “Return to automatic”, gives the automatic layout back.', 'info', 6000)
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
