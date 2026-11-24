/**
 * A candidate edited on the scope diagram's canvas (06·5, F12): the diagram editor's own session
 * (`useDiagramEditing`), with every content command recorded at once in the candidate as an edit
 * (`candidateCanvas.editsOf`), so the candidate saves as you go and the diagram is never written.
 * *Remove from view* is the session's own removal and records nothing.
 *
 * **Undo reverts what was recorded, not only the picture.** Each content step the session takes is
 * remembered with the operations the candidate held after it was recorded, keyed by the session's own
 * list of commands — which a move or a removal from view carries over unchanged. When Undo or Redo
 * returns the session to a list it has held before, the candidate is written back to the operations it
 * held then, through the candidate's versioned edit. So an undone create takes its relations with it
 * and an undone removal brings back the edits the removal dropped, exactly as the server recorded them.
 */
import { ref, watch, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import { chosenIds, commandsOf, editsOf, operationsOf } from '../../domain/stressAnalysis/candidateCanvas'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { formatEffectError } from '../lib/errors'
import type { DiagramEditing } from './useDiagramEditing'
import { useDiagramEditing } from './useDiagramEditing'

/** The key of a session state that holds no content commands yet. */
const NONE: readonly CanvasCommand[] = Object.freeze([])

export function useCandidateEditing(
  svc: ModelService, diagramId: () => string, membership: () => DrawnMembership | null,
  candidateId: () => string, onRecorded: () => void,
): DiagramEditing & { readonly savedAt: Ref<string | null> } {
  const editing = useDiagramEditing(svc, diagramId, membership)
  const savedAt = ref<string | null>(null)
  let version = ''
  /** The candidate's `changes` as it stands now, and as it stood after each list of commands was recorded. */
  let held: unknown = null
  const recordedAt = new Map<readonly CanvasCommand[], unknown>()
  /** One write at a time, in the order they were asked for: each states the version the one before answered. */
  let writing: Promise<unknown> = Promise.resolve()

  const commandsNow = (): readonly CanvasCommand[] => editing.session.state.value?.commands ?? NONE
  const stamp = () => { savedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
  const queued = <T>(write: () => Promise<T>): Promise<T> => {
    const next = writing.then(write, write)
    writing = next.catch(() => undefined)
    return next
  }

  /** Read the candidate, and open the canvas with what it already creates, renames and connects drawn. */
  const open = async (): Promise<boolean> => {
    try {
      const [read, composed] = await Promise.all([
        Effect.runPromise(svc.readCandidate(candidateId())),
        Effect.runPromise(svc.compareCandidate(candidateId(), 'model')),
      ])
      version = read.version
      held = read.record.changes
      recordedAt.clear()
      const opened = await editing.open(commandsOf(operationsOf(read.record), chosenIds(composed.view)))
      recordedAt.set(commandsNow(), held)
      return opened
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
      return false
    }
  }

  /** Draw the command, then record it in the candidate; a refused record says why on the canvas. */
  const propose = async (command: CanvasCommand, overlay?: Record<string, unknown>): Promise<boolean> => {
    if (!(await editing.propose(command, overlay))) return false
    const drawn = commandsNow()
    try {
      await queued(async () => {
        for (const edit of editsOf(command)) {
          const answer = await Effect.runPromise(svc.recordOperation(candidateId(), version, edit))
          version = answer.version
          held = answer.record.changes
        }
      })
      recordedAt.set(drawn, held)
      stamp()
      onRecorded()
      return true
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
      return false
    }
  }

  /** The candidate written back to *changes*, the operations it held when the session last showed this. */
  const restore = async (changes: unknown): Promise<void> => {
    try {
      const wrote = await queued(async () => {
        if (changes === held) return false
        const answer = await Effect.runPromise(svc.editCandidate(candidateId(), version, { changes }))
        version = answer.version
        held = changes
        return true
      })
      if (!wrote) return
      stamp()
      onRecorded()
    } catch (failure) {
      editing.error.value = formatEffectError(failure)
    }
  }

  // Undo and Redo show a list of commands the session held before; a new step shows one it has not. The
  // comparison is made in the queue, after any record still in flight has answered.
  watch(commandsNow, (now) => {
    const then = recordedAt.get(now)
    if (then !== undefined) void restore(then)
  }, { flush: 'sync' })

  return { ...editing, open, propose, savedAt }
}
