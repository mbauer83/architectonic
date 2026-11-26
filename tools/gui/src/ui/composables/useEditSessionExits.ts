/**
 * The ways out of an edit session that has unsaved changes, and the question each asks first (D15, Q2).
 *
 * - **Leaving** — Done, Escape, or opening another page — asks in the edit bar: *Save and exit*,
 *   *Discard and exit* or *Keep editing*. A navigation held by the question goes on once it is answered
 *   by saving or discarding, and is dropped by *Keep editing*.
 * - **Discard** asks whether to throw the changes away; *Cancel* is the answer it starts on, and Escape
 *   gives the same answer.
 * - **Closing the tab or reloading** is asked about by the browser, in its own words.
 *
 * With nothing unsaved, none of them asks.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

export interface EditSessionEnds {
  /** Whether the session is open and holds a change Save would write. */
  readonly unsaved: () => boolean
  /** Write the session; answers whether it was written. */
  readonly save: () => Promise<boolean>
  /** Throw the session's changes away, back to the last save. */
  readonly discard: () => void
  /** Close the session and show the picture as saved. */
  readonly close: () => void
}

export function useEditSessionExits(ends: EditSessionEnds) {
  /** Whether the leave question is showing. */
  const leaving = ref(false)
  /** Whether the discard question is showing. */
  const discarding = ref(false)
  /** The navigation the leave question holds, which goes on once it is answered by leaving. */
  let onward: (() => void) | null = null

  const exit = () => {
    leaving.value = false
    discarding.value = false
    ends.close()
    const then = onward
    onward = null
    then?.()
  }

  /** Done, or Escape with nothing else to close: leave, or ask how when something is unsaved. */
  const done = () => {
    discarding.value = false
    if (ends.unsaved()) leaving.value = true
    else exit()
  }
  const saveAndExit = async () => { if (await ends.save()) exit() }
  const discardAndExit = () => { ends.discard(); exit() }
  const keepEditing = () => {
    leaving.value = false
    onward = null
  }
  /** The leave question set aside while the changes are reviewed before saving; a navigation it held waits. */
  const reviewChanges = () => { leaving.value = false }

  /**
   * Whether the page may be left now. Where it may not, the leave question is asked, and *proceed* is
   * what answering it by saving or discarding goes on to do.
   */
  const mayLeave = (proceed: () => void): boolean => {
    if (!ends.unsaved()) return true
    discarding.value = false
    leaving.value = true
    onward = proceed
    return false
  }

  /** Discard: asked first where there is something to discard. */
  const askDiscard = () => { if (ends.unsaved()) discarding.value = true }
  const confirmDiscard = () => {
    discarding.value = false
    ends.discard()
  }
  const cancelDiscard = () => { discarding.value = false }

  /** Escape on an open question answers it the safe way; answers whether there was one to answer. */
  const answerEscape = (): boolean => {
    if (discarding.value) cancelDiscard()
    else if (leaving.value) keepEditing()
    else return false
    return true
  }

  /** Every question closed and every held navigation dropped: the session is gone. */
  const forget = () => {
    leaving.value = false
    discarding.value = false
    onward = null
  }

  const onBeforeUnload = (event: BeforeUnloadEvent) => {
    if (!ends.unsaved()) return
    // The browser asks, in its own words: a page may only say that there is something to ask about.
    event.preventDefault()
  }
  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

  return {
    leaving, discarding, done, saveAndExit, discardAndExit, keepEditing, reviewChanges, mayLeave,
    askDiscard, confirmDiscard, cancelDiscard, answerEscape, forget,
  }
}

export type EditSessionExits = ReturnType<typeof useEditSessionExits>
