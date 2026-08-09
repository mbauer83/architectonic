import { computed, ref, type Ref } from 'vue'
import type { Scratchpad } from '../../domain/schemas/scratchpads'

/**
 * The scratchpad the canvas is editing, its undo history, and when it is worth saving.
 *
 * **Every edit is a whole new document.** That is what makes undo a matter of keeping previous
 * values rather than of computing inverses for each kind of edit — and inverse-per-edit is how undo
 * stacks acquire the bug where one operation type is not quite reversible. The documents are small
 * and shallow-shared, so a hundred of them cost little.
 *
 * **Saving is debounced here, in the browser, never on the server.** A server-side debounce would
 * still cost one request per drag, and the shape the write path is least able to absorb is many
 * small writes: the release before this one was spent on exactly that. The endpoint sees a save;
 * it never sees a drag.
 */

/** Idle time before a change is written. Long enough that a drag, a rename or a burst of typing is
 * one save; short enough that nobody watches a spinner wondering whether their work is safe. */
export const SAVE_DEBOUNCE_MS = 1000

/** How deep the undo history goes. Bounded because a canvas session is long and each entry pins a
 * whole document; fifty is far past what anyone reaches for and costs nothing at these sizes. */
export const UNDO_DEPTH = 50

export interface ScratchpadDocument {
  readonly current: Ref<Scratchpad | null>
  readonly dirty: Ref<boolean>
  readonly canUndo: Ref<boolean>
  readonly canRedo: Ref<boolean>
  /** Replace the document, pushing the previous one onto the undo stack. */
  readonly commit: (next: Scratchpad) => void
  /** Adopt a document without making it undoable — a load, or the server's answer to a save. */
  readonly adopt: (next: Scratchpad) => void
  readonly undo: () => void
  readonly redo: () => void
}

export function useScratchpadDocument(): ScratchpadDocument {
  const current = ref<Scratchpad | null>(null)
  const past = ref<Scratchpad[]>([])
  const future = ref<Scratchpad[]>([])
  const dirty = ref(false)

  const commit = (next: Scratchpad): void => {
    if (current.value) {
      past.value = [...past.value, current.value].slice(-UNDO_DEPTH)
    }
    // A new edit discards the redo branch: keeping it would let a redo reinstate a document that
    // was never in this history, which is the one thing an undo stack must not do.
    future.value = []
    current.value = next
    dirty.value = true
  }

  const adopt = (next: Scratchpad): void => {
    current.value = next
    dirty.value = false
  }

  const undo = (): void => {
    const previous = past.value.at(-1)
    if (!previous || !current.value) return
    future.value = [...future.value, current.value]
    past.value = past.value.slice(0, -1)
    current.value = previous
    dirty.value = true
  }

  const redo = (): void => {
    const next = future.value.at(-1)
    if (!next || !current.value) return
    past.value = [...past.value, current.value]
    future.value = future.value.slice(0, -1)
    current.value = next
    dirty.value = true
  }

  return {
    current,
    dirty,
    canUndo: computed(() => past.value.length > 0),
    canRedo: computed(() => future.value.length > 0),
    commit,
    adopt,
    undo,
    redo,
  }
}
